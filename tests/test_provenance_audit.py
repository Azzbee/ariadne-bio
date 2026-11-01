"""Independent path/world oracles for correlated provenance and exact protection."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

import numpy as np
import pytest

from app.binding_audit import certificate_digest
from app.provenance_audit import ProvenanceAuditor
from tests.test_binding_audit import _make_graph, _oracle
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def _annotated_graph(seed):
    graph = _make_graph(seed)
    rng = np.random.default_rng(seed + 100)
    for edge in graph["edges"]:
        if edge["type"] == "BINDS":
            edge["sources"] = [name for name in ("A", "B", "C", "D") if rng.random() < 0.45]
            edge["data"]["pubmed_ids"] = [
                str(100 + index) for index in range(3) if rng.random() < 0.55
            ]
    return graph


def _memberships(graph, kind):
    groups = {}
    for edge in graph["edges"]:
        if edge["type"] != "BINDS":
            continue
        labels = edge["sources"] if kind == "source" else edge["data"].get("pubmed_ids", [])
        for label in labels:
            groups.setdefault(f"{kind}:{label}", set()).add(edge["id"])
    return groups


def _worlds(graph, model, disease, memberships, protected=(), budget=2):
    """Independent literal-record union, literal paths, scalar score and ranking."""
    allowed = sorted(set(memberships) - set(protected))
    result = []
    for size in range(budget + 1):
        for groups in itertools.combinations(allowed, size):
            removed = set().union(*(memberships[group] for group in groups)) if groups else set()
            result.append((groups, _oracle(graph, model, disease, removed)))
    return result


def _optimal_plans(worlds, compound, top_k, memberships, protected):
    """Enumerate every condition, not the production hitting-set implementation."""
    available = sorted(set(memberships) - set(protected))
    for size in range(len(available) + 1):
        valid = []
        for condition in itertools.combinations(available, size):
            remaining = [
                states[compound] for groups, states in worlds if not set(groups) & set(condition)
            ]
            if all(state["supported"] and state["rank"] <= top_k for state in remaining):
                valid.append(list(condition))
        if valid:
            return valid
    return []


@pytest.mark.parametrize("seed", range(8))
@pytest.mark.parametrize("kind", ["source", "pubmed"])
def test_group_bounds_and_all_minimum_plans_match_independent_oracle(tmp_path, seed, kind):
    graph = _annotated_graph(seed)
    engine = create_fixture_engine(tmp_path, graph)
    rng = np.random.default_rng(seed + 50)
    engine.model.update(
        coefficients=rng.uniform(-3, 3, 8).tolist(),
        mean=rng.uniform(-1, 1, 8).tolist(),
        scale=rng.uniform(0.2, 2, 8).tolist(),
        intercept=float(rng.normal()),
    )
    auditor = ProvenanceAuditor(engine)
    memberships = _memberships(graph, kind)
    for disease in engine.entities["Disease"]:
        for protected in ((), tuple(sorted(memberships)[:1])):
            worlds = _worlds(graph, engine.model, disease, memberships, protected)
            for compound in engine.entities["Compound"]:
                certificate = auditor.audit(
                    disease,
                    compound,
                    top_k=2,
                    group_kind=kind,
                    group_ids=sorted(memberships),
                    protected_group_ids=protected,
                )
                baseline = worlds[0][1][compound]
                assert {key: certificate["baseline"][key] for key in baseline} == baseline
                for row in certificate["results"]:
                    subset = [
                        (groups, states[compound])
                        for groups, states in worlds
                        if len(groups) <= row["budget"]
                    ]
                    ranks = [state["rank"] for _, state in subset if state["supported"]]
                    unsupported = any(not state["supported"] for _, state in subset)
                    assert row["scenario_count"] == len(subset)
                    assert row["worst_supported_rank"] == max(ranks, default=None)
                    assert row["unsupported_attainable"] == unsupported
                    assert row["robust"] == (not unsupported and max(ranks, default=3) <= 2)
                    for name in ("rank_witness", "unsupported_witness"):
                        witness = row[name]
                        if witness is None:
                            continue
                        expected = next(
                            state
                            for groups, state in subset
                            if list(groups) == witness["group_ids"]
                        )
                        assert witness["focus"]["after"] == expected
                        assert (
                            auditor.replay(disease, compound, witness["group_ids"], kind)["focus"]
                            == expected
                        )
                plans = _optimal_plans(worlds, compound, 2, memberships, protected)
                plan = certificate["protection_plan"]
                assert plan["minimum_additional_groups"] == (len(plans[0]) if plans else None)
                assert plan["optimal_set_count"] == len(plans)
                assert plan["optimal_sets_preview"] == plans[:12]
                assert plan["representative"] == (plans[0] if plans else [])
                assert auditor.verify(certificate)["valid"]


def test_overlaps_remove_union_once_and_protection_does_not_immunize_records(tmp_path):
    graph = tiny_graph()
    for edge in graph["edges"]:
        if edge["type"] == "BINDS":
            edge["sources"] = ["A", "B", "A"]
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path, graph))
    certificate = auditor.audit("Disease::D1", "Compound::C2", top_k=1)
    assert certificate["scope"]["eligible_group_count"] == 2
    assert certificate["results"][2]["scenario_count"] == 4
    assert (
        auditor.replay("Disease::D1", "Compound::C2", ["source:A", "source:B"])[
            "removed_edge_count"
        ]
        == 3
    )
    assert certificate["protection_plan"]["representative"] == ["source:A", "source:B"]
    conditional = auditor.audit(
        "Disease::D1", "Compound::C2", top_k=1, protected_group_ids=["source:A"]
    )
    assert not conditional["results"][2]["robust"]
    assert conditional["protection_plan"]["representative"] == ["source:B"]
    secured = auditor.audit(
        "Disease::D1", "Compound::C2", top_k=1, protected_group_ids=["source:A", "source:B"]
    )
    assert secured["results"][2]["robust"]
    assert secured["results"][2]["scenario_count"] == 1
    assert secured["protection_plan"]["minimum_additional_groups"] == 0


def test_one_group_can_promote_multiple_rivals_with_focus_unchanged(tmp_path):
    graph = _make_graph()
    graph["edges"] = []
    for compound, targets in ((0, [0, 1, 2]), (1, [0, 1, 2]), (2, [1, 2])):
        for gene in targets:
            graph["edges"].append(
                {
                    "id": f"b{compound}-{gene}",
                    "source": f"Compound::{compound}",
                    "target": f"Gene::{gene}",
                    "type": "BINDS",
                    "sources": ["shared"] if gene == 0 else [],
                    "data": {},
                }
            )
    graph["edges"].extend(
        {
            "id": f"a{gene}",
            "source": "Disease::0",
            "target": f"Gene::{gene}",
            "type": "ASSOCIATES",
            "sources": [],
            "data": {},
        }
        for gene in (1, 2)
    )
    engine = create_fixture_engine(tmp_path, graph)
    engine.model["coefficients"] = [0, 0, 0, 0, 0, 0, -1, 0]
    auditor = ProvenanceAuditor(engine)
    certificate = auditor.audit("Disease::0", "Compound::2", top_k=1, budget=1)
    assert [row["worst_supported_rank"] for row in certificate["results"]] == [1, 3]
    witness = certificate["results"][1]["rank_witness"]
    assert witness["affected_compound_count"] == 2
    assert witness["focus"]["before"] == {**witness["focus"]["after"], "rank": 1}
    assert auditor.verify(certificate)["valid"]


def test_greedy_baseline_is_feasible_but_does_not_claim_optimality(tmp_path):
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path, _annotated_graph(5)))
    for disease in auditor.engine.entities["Disease"]:
        for compound in auditor.engine.entities["Compound"]:
            exact = auditor.audit(disease, compound, top_k=2)
            greedy = auditor.greedy_protection(disease, compound, top_k=2)
            minimum = exact["protection_plan"]["minimum_additional_groups"]
            if minimum is None:
                assert not greedy["conditional_robust"]
                continue
            conditional = auditor.audit(
                disease, compound, top_k=2, protected_group_ids=greedy["protected_group_ids"]
            )
            assert conditional["results"][2]["robust"]
            assert greedy["additional_group_count"] >= minimum
            assert "no minimum-cardinality guarantee" in greedy["guarantee"]


def test_exact_minimum_alternative_count_survives_preview_truncation():
    from app.provenance_audit import _State

    groups = tuple(f"source:{index:02d}" for index in range(16))
    states = []
    for size in range(3):
        for selected in itertools.combinations(groups, size):
            state = _State(
                np.array([[1, 0, 0]]),
                np.array([0.5]),
                np.array([0.0]),
                np.array([2 if size == 2 else 1]),
            )
            states.append((selected, state))
    plan = ProvenanceAuditor._protection(states, 0, 1, groups)
    assert plan["minimum_additional_groups"] == 15
    assert plan["optimal_set_count"] == 16
    assert len(plan["optimal_sets_preview"]) == 12
    assert plan["alternatives_truncated"]


def test_catalog_without_model_and_missing_annotations_are_explicit(tmp_path):
    graph = tiny_graph()
    graph["edges"][0]["sources"] = []
    engine = create_fixture_engine(tmp_path, graph)
    engine.model = None
    auditor = ProvenanceAuditor(engine)
    catalog = auditor.catalog()
    assert catalog["coverage"] == {
        "binding_edges": 3,
        "annotated_binding_edges": 2,
        "unannotated_binding_edges": 1,
    }
    assert auditor.catalog("pubmed")["total"] == 0
    with pytest.raises(RuntimeError, match="fitted model"):
        auditor.audit("Disease::D1", "Compound::C1")


def test_empty_source_catalog_is_baseline_only(tmp_path):
    graph = tiny_graph()
    for edge in graph["edges"]:
        edge["sources"] = []
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path, graph))
    certificate = auditor.audit("Disease::D1", "Compound::C2", top_k=1)
    assert certificate["scope"]["groups"] == []
    assert all(row["robust"] and row["scenario_count"] == 1 for row in certificate["results"])
    assert certificate["protection_plan"]["status"] == "already_robust"


@pytest.mark.parametrize(
    "settings",
    [
        {"budget": True},
        {"budget": 3},
        {"budget": -1},
        {"top_k": 0},
        {"top_k": 101},
        {"group_kind": "study"},
        {"group_kind": "pubmed"},
        {"group_kind": "pubmed", "group_ids": []},
        {"group_ids": ["source:unknown"]},
        {"group_ids": [True]},
        {"group_ids": "source:x"},
        {"group_ids": ["source:Hand-counted fixture"] * 2},
        {"protected_group_ids": ["source:unknown"]},
        {"protected_group_ids": [False]},
        {"protected_group_ids": ["source:Hand-counted fixture"] * 2},
    ],
)
def test_invalid_scope_cannot_be_silently_narrowed(tmp_path, settings):
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path))
    with pytest.raises(ValueError):
        auditor.audit("Disease::D1", "Compound::C1", **settings)


def test_more_than_sixteen_groups_require_explicit_bounded_selection(tmp_path):
    graph = tiny_graph()
    graph["edges"][0]["sources"] = [f"S{index}" for index in range(17)]
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path, graph))
    with pytest.raises(ValueError, match="16"):
        auditor.audit("Disease::D1", "Compound::C1")
    result = auditor.audit(
        "Disease::D1", "Compound::C1", group_ids=[f"source:S{i}" for i in range(16)]
    )
    assert result["proof"]["scenarios_evaluated"] == 137


@pytest.mark.parametrize("mutation", ["rank", "plan", "groups", "preview", "identity", "scope"])
def test_rehashed_false_claims_are_rejected(tmp_path, mutation):
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path))
    certificate = auditor.audit("Disease::D1", "Compound::C2")
    if mutation == "rank":
        certificate["results"][2]["worst_supported_rank"] += 1
    elif mutation == "plan":
        certificate["protection_plan"]["minimum_additional_groups"] = 0
    elif mutation == "groups":
        certificate["results"][1]["unsupported_witness"]["removed_edge_count"] = 1
    elif mutation == "preview":
        certificate["results"][1]["unsupported_witness"]["removed_edges_preview"][0]["sources"] = [
            "invented"
        ]
    elif mutation == "identity":
        certificate["identity"]["group_map_sha256"] = "0" * 64
    else:
        certificate["scope"]["operation"] = "withdraw_if_all_supporting_sources_removed"
    certificate["certificate_sha256"] = certificate_digest(certificate)
    verified = auditor.verify(certificate)
    assert not verified["valid"]
    assert verified["checks"][0] == "Certificate content checksum matches"


def test_browser_number_roundtrip_and_one_ulp_change(tmp_path):
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path))
    original = auditor.audit("Disease::D1", "Compound::C1")
    encoded = subprocess.run(
        [
            "node",
            "-e",
            "let s=''; process.stdin.on('data',x=>s+=x); "
            "process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(s))))",
        ],
        input=json.dumps(original),
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert auditor.verify(json.loads(encoded))["valid"]
    changed = deepcopy(original)
    changed["baseline"]["score"] = np.nextafter(changed["baseline"]["score"], 1.0).item()
    changed["certificate_sha256"] = certificate_digest(changed)
    assert not auditor.verify(changed)["valid"]


def test_cache_isolation_deterministic_threads_and_legacy_model_immutability(tmp_path):
    engine = create_fixture_engine(tmp_path)
    auditor = ProvenanceAuditor(engine, cache_size=1)
    original = auditor.audit("Disease::D1", "Compound::C1")
    engine.model["coefficients"] = [10] * 8
    mutated = auditor.audit("Disease::D1", "Compound::C1")
    assert mutated == original
    mutated["scope"]["groups"][0]["label"] = "corruption"
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: auditor.audit("Disease::D1", "Compound::C1"), range(8)))
    assert all(value == original for value in results)
    assert auditor.verify(original)["valid"]
    auditor.audit("Disease::D2", "Compound::C2")
    assert auditor.audit("Disease::D1", "Compound::C1") == original


@pytest.mark.parametrize(
    "value", [None, [], {"certificate_sha256": "bad"}, {"value": float("nan")}]
)
def test_malformed_certificate_returns_invalid_without_crashing(tmp_path, value):
    auditor = ProvenanceAuditor(create_fixture_engine(tmp_path))
    assert not auditor.verify(value)["valid"]


@pytest.mark.parametrize("duplicate_id", [True, False])
def test_duplicate_record_or_binary_coordinate_cannot_be_certified(tmp_path, duplicate_id):
    graph = tiny_graph()
    duplicate = deepcopy(graph["edges"][0])
    if not duplicate_id:
        duplicate["id"] = "new-id-same-edge"
    graph["edges"].append(duplicate)
    with pytest.raises(ValueError, match="Duplicate"):
        ProvenanceAuditor(create_fixture_engine(tmp_path, graph))


@pytest.mark.parametrize("bad", [None, "provider", [1], [""], [" "]])
def test_malformed_annotation_lists_are_rejected(tmp_path, bad):
    graph = tiny_graph()
    graph["edges"][0]["sources"] = bad
    with pytest.raises(ValueError, match="annotations"):
        ProvenanceAuditor(create_fixture_engine(tmp_path, graph))


def test_source_hash_changes_when_only_imported_provenance_changes(tmp_path):
    graph = tiny_graph()
    first = ProvenanceAuditor(create_fixture_engine(tmp_path, graph))
    original = first.audit("Disease::D1", "Compound::C1")
    graph["edges"][0]["data"]["pubmed_ids"] = ["123"]
    second = ProvenanceAuditor(create_fixture_engine(tmp_path, graph))
    assert (
        first.catalog()["identity"]["group_map_sha256"]
        != second.catalog()["identity"]["group_map_sha256"]
    )
    assert not second.verify(original)["valid"]


@pytest.mark.parametrize("change", ["interaction", "pathway", "node", "duplicate_node"])
def test_graph_identity_cannot_change_between_engine_and_auditor_load(tmp_path, change):
    graph = tiny_graph()
    engine = create_fixture_engine(tmp_path, graph)
    if change in ("interaction", "pathway"):
        relation = "INTERACTS" if change == "interaction" else "PARTICIPATES"
        remove = next(edge for edge in graph["edges"] if edge["type"] == relation)
        graph["edges"].remove(remove)
    elif change == "node":
        graph["nodes"][0]["name"] = "changed after load"
    else:
        graph["nodes"].append(deepcopy(graph["nodes"][0]))
    (tmp_path / "graph.json").write_text(json.dumps(graph))
    with pytest.raises(ValueError, match="changed|node"):
        ProvenanceAuditor(engine)


def test_checksummed_model_parameters_cannot_change_under_old_identity(tmp_path):
    engine = create_fixture_engine(tmp_path)
    engine.model["model_sha256"] = hashlib.sha256(
        json.dumps(engine.model, sort_keys=True).encode()
    ).hexdigest()
    engine.model["coefficients"][0] += 0.1
    with pytest.raises(ValueError, match="Model checksum changed"):
        ProvenanceAuditor(engine)


@pytest.mark.full_data
def test_real_provenance_case_has_bounded_certificate_and_independent_replay():
    from app.graph_engine import GraphEngine

    data_dir = Path("data/processed")
    if not (data_dir / "graph.json").exists():
        pytest.skip("Prepared full data unavailable")
    engine = GraphEngine(data_dir)
    auditor = ProvenanceAuditor(engine)
    disease = next(
        key
        for key in engine.entities["Disease"]
        if engine.nodes[key]["name"] == "rheumatoid arthritis"
    )
    compound = next(
        key for key in engine.entities["Compound"] if engine.nodes[key]["name"] == "Marimastat"
    )
    certificate = auditor.audit(disease, compound)
    assert len(certificate["scope"]["groups"]) == 14
    assert len(json.dumps(certificate).encode()) < 256 * 1024
    replay = auditor.replay(disease, compound, ["source:DrugBank (target)"])
    assert replay["focus"]["rank"] == 1096
    assert replay["removed_edge_count"] == 4603
    assert auditor.verify(certificate)["valid"]
