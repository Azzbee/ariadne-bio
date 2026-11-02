"""Independent literal-path oracles for the complete mixed action rectangle."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import itertools
import json

import numpy as np
import pytest

from app.binding_audit import BindingAuditor, certificate_digest
from app.mixed_audit import METHOD, MixedAuditor
from app.provenance_audit import ProvenanceAuditor
from tests.test_binding_audit import _make_graph, _oracle
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def _grouped_graph(seed):
    graph = _make_graph(seed)
    rng = np.random.default_rng(seed + 701)
    for edge in graph["edges"]:
        if edge["type"] == "BINDS":
            edge["sources"] = [f"Source {i}" for i in range(3) if rng.random() < 0.5]
            edge["data"]["pubmed_ids"] = [str(100 + i) for i in range(2) if rng.random() < 0.5]
    return graph


def _literal_groups(graph, kind="source"):
    groups = {}
    for edge in graph["edges"]:
        if edge["type"] != "BINDS":
            continue
        labels = edge["sources"] if kind == "source" else edge["data"].get("pubmed_ids", [])
        for label in labels:
            groups.setdefault(f"{kind}:{label}", set()).add(edge["id"])
    return groups


def _enumerate_actions(graph, model, disease, groups):
    edges = {edge["id"] for edge in graph["edges"] if edge["type"] == "BINDS"}
    rows, cache = [], {}
    for selected in ((), *((key,) for key in sorted(groups))):
        grouped = groups[selected[0]] if selected else set()
        for residual in ((), *((key,) for key in sorted(edges - grouped))):
            union = frozenset(grouped | set(residual))
            if union not in cache:
                # Literal paths and independent Decimal scalar arithmetic: no
                # production envelopes, rank helper, matrix replay or score cache.
                cache[union] = _oracle(graph, model, disease, union)
            rows.append((selected, residual, cache[union]))
    return rows


def _objective(states, compound, top_k):
    focus = states[compound]
    rivals = sorted(
        (value for key, value in states.items() if key != compound and value["supported"]),
        key=lambda value: value["rank"],
    )
    threshold = rivals[top_k - 1]["score"] if len(rivals) >= top_k else -np.inf
    return (
        -(focus["rank"] if focus["supported"] else len(states) + 1),
        focus["score"] - threshold,
        focus["score"],
    )


def _literal_greedy(actions, groups, compound, top_k):
    def choice_key(row):
        selected, residual, states = row
        return (
            _objective(states, compound, top_k),
            len(selected) + len(residual),
            selected,
            residual,
        )

    first_group = min((row for row in actions if not row[1]), key=choice_key)[0]
    source_first = min((row for row in actions if row[0] == first_group), key=choice_key)
    first_edge = min((row for row in actions if not row[0]), key=choice_key)[1]
    choices = []
    for selected in ((), *((key,) for key in sorted(groups))):
        residual = () if selected and set(first_edge) & groups[selected[0]] else first_edge
        choices.append(next(row for row in actions if row[:2] == (selected, residual)))
    edge_first = min(choices, key=choice_key)
    return source_first, edge_first, min((source_first, edge_first), key=choice_key)


@pytest.mark.parametrize("seed", range(12))
def test_complete_rectangle_and_two_order_greedy_match_literal_oracle(tmp_path, seed):
    graph = _grouped_graph(seed)
    engine = create_fixture_engine(tmp_path, graph)
    rng = np.random.default_rng(seed + 971)
    engine.model.update(
        coefficients=rng.uniform(-3, 3, 8).tolist(),
        mean=rng.uniform(-1, 1, 8).tolist(),
        scale=rng.uniform(0.1, 2, 8).tolist(),
        intercept=float(rng.uniform(-3, 3)),
    )
    auditor = MixedAuditor(engine)
    groups = _literal_groups(graph)
    for disease in engine.entities["Disease"]:
        actions = _enumerate_actions(graph, engine.model, disease, groups)
        for compound, top_k in itertools.product(engine.entities["Compound"], (1, 3)):
            certificate = auditor.audit(disease, compound, top_k=top_k)
            assert certificate["method"] == METHOD
            assert certificate["identity"]["scorer"] == "decimal80-binary64-v1"
            for row in certificate["results"]:
                permitted = [
                    (selected, residual, states)
                    for selected, residual, states in actions
                    if len(selected) <= row["group_budget"] and len(residual) <= row["edge_budget"]
                ]
                supported = [
                    states[compound]["rank"]
                    for _, _, states in permitted
                    if states[compound]["supported"]
                ]
                missing = any(not states[compound]["supported"] for _, _, states in permitted)
                assert row["worst_supported_rank"] == (max(supported) if supported else None)
                assert row["unsupported_attainable"] == missing
                assert row["robust"] == (
                    not missing and bool(supported) and max(supported) <= top_k
                )
                assert row["covered_action_representations"] == len(permitted)
                for name in ("rank_witness", "unsupported_witness"):
                    witness = row[name]
                    if witness is None:
                        continue
                    key = tuple(witness["group_ids"]), tuple(witness["residual_edge_ids"])
                    oracle_state = next(
                        states[compound]
                        for selected, residual, states in permitted
                        if (selected, residual) == key
                    )
                    assert witness["focus"]["after"] == oracle_state
                    assert auditor.replay(disease, compound, *key)["focus"] == oracle_state
            verification = auditor.verify(certificate)
            assert verification["valid"], verification
            greedy = auditor.greedy(disease, compound, top_k=top_k)
            expected = _literal_greedy(actions, groups, compound, top_k)
            for name, (selected, residual, states) in zip(
                ("source_first", "edge_first", "strongest"), expected
            ):
                assert greedy[name]["group_ids"] == list(selected)
                assert greedy[name]["residual_edge_ids"] == list(residual)
                assert greedy[name]["focus"] == states[compound]


def test_zero_axes_match_existing_independent_auditors(tmp_path):
    graph = _grouped_graph(4)
    engine = create_fixture_engine(tmp_path, graph)
    mixed, bindings, provenance = (
        MixedAuditor(engine),
        BindingAuditor(engine),
        ProvenanceAuditor(engine),
    )
    for disease, compound in itertools.product(
        engine.entities["Disease"], engine.entities["Compound"]
    ):
        certificate = mixed.audit(disease, compound, top_k=2)
        edge = bindings.audit(disease, compound, top_k=2, budget=1)["results"][1]
        group = provenance.audit(disease, compound, top_k=2, budget=1)["results"][1]
        for row, reference, robust_key in (
            (certificate["results"][1], edge, "top_k_robust"),
            (certificate["results"][2], group, "robust"),
        ):
            assert row["worst_supported_rank"] == reference["worst_supported_rank"]
            assert row["unsupported_attainable"] == reference["unsupported_attainable"]
            assert row["robust"] == reference[robust_key]


@pytest.mark.parametrize("group_budget,edge_budget", list(itertools.product((0, 1), repeat=2)))
def test_requested_rectangle_includes_exactly_its_prefixes(tmp_path, group_budget, edge_budget):
    auditor = MixedAuditor(create_fixture_engine(tmp_path))
    cert = auditor.audit(
        "Disease::D1", "Compound::C2", group_budget=group_budget, edge_budget=edge_budget
    )
    assert [(row["group_budget"], row["edge_budget"]) for row in cert["results"]] == list(
        itertools.product(range(group_budget + 1), range(edge_budget + 1))
    )
    assert auditor.verify(cert)["valid"]


@pytest.mark.parametrize(
    "coefficients,intercept",
    [([0] * 8, 0), ([0] * 8, 900), ([0] * 8, -900), ([0, 0, 0, 0, 0, 0, -1, 0], 0)],
)
def test_ties_saturation_and_nonmonotone_competitor_promotion(tmp_path, coefficients, intercept):
    graph = _grouped_graph(2)
    engine = create_fixture_engine(tmp_path, graph)
    engine.model.update(coefficients=coefficients, intercept=intercept)
    auditor = MixedAuditor(engine)
    actions = _enumerate_actions(graph, engine.model, "Disease::0", _literal_groups(graph))
    for compound in engine.entities["Compound"]:
        cert = auditor.audit("Disease::0", compound)
        ranks = [
            states[compound]["rank"] for _, _, states in actions if states[compound]["supported"]
        ]
        assert cert["results"][-1]["worst_supported_rank"] == (max(ranks) if ranks else None)
        assert auditor.verify(cert)["valid"]


def test_overlap_and_unannotated_edges_preserve_residual_semantics(tmp_path):
    graph = tiny_graph()
    bindings = [edge for edge in graph["edges"] if edge["type"] == "BINDS"]
    bindings[0]["sources"] = ["Shared", "Other"]
    bindings[1]["sources"] = ["Shared"]
    bindings[2]["sources"] = []
    auditor = MixedAuditor(create_fixture_engine(tmp_path, graph))
    cert = auditor.audit("Disease::D1", "Compound::C3", group_ids=["source:Shared"])
    assert cert["scope"]["groups"][0]["edge_count"] == 2
    combined = cert["results"][-1]["unsupported_witness"]
    assert combined is not None
    replay = auditor.replay("Disease::D1", "Compound::C3", ["source:Shared"], [bindings[2]["id"]])
    assert replay["removed_edge_count"] == 3
    assert not replay["focus"]["supported"]
    with pytest.raises(ValueError, match="survive"):
        auditor.replay("Disease::D1", "Compound::C3", ["source:Shared"], [bindings[0]["id"]])


def test_separately_robust_support_can_fail_only_when_actions_combine(tmp_path):
    graph = tiny_graph()
    for edge in graph["edges"]:
        if edge["type"] == "BINDS":
            edge["sources"] = ["A"] if edge["source"] == "Compound::C2" else []
    graph["edges"].append(
        {
            "id": "extra-binding",
            "source": "Compound::C2",
            "target": "Gene::G1",
            "type": "BINDS",
            "sources": ["B"],
            "license": None,
            "data": {},
        }
    )
    auditor = MixedAuditor(create_fixture_engine(tmp_path, graph))
    certificate = auditor.audit("Disease::D1", "Compound::C2", top_k=100)
    assert certificate["results"][1]["robust"]
    assert certificate["results"][2]["robust"]
    mixed = certificate["results"][3]
    assert not mixed["robust"] and mixed["unsupported_attainable"]
    witness = mixed["unsupported_witness"]
    assert len(witness["group_ids"]) == len(witness["residual_edge_ids"]) == 1
    assert auditor.verify(certificate)["valid"]


def test_mixed_rival_promotion_can_break_two_separate_top_one_certificates(tmp_path):
    graph = _make_graph(0)
    graph["edges"] = []
    for compound, genes in (("Compound::0", range(4)), ("Compound::1", range(2))):
        for gene in genes:
            graph["edges"].append(
                {
                    "id": f"b-{compound}-{gene}",
                    "source": compound,
                    "target": f"Gene::{gene}",
                    "type": "BINDS",
                    "sources": ["Rival source"] if compound == "Compound::0" and gene == 0 else [],
                    "license": None,
                    "data": {},
                }
            )
    for gene in range(4):
        graph["edges"].append(
            {
                "id": f"a-{gene}",
                "source": "Disease::0",
                "target": f"Gene::{gene}",
                "type": "ASSOCIATES",
                "sources": [],
                "license": None,
                "data": {},
            }
        )
    engine = create_fixture_engine(tmp_path, graph)
    engine.model["coefficients"] = [0, 0, 0, 0, 0, 0, -1, 0]
    auditor = MixedAuditor(engine)
    certificate = auditor.audit("Disease::0", "Compound::1", top_k=1)
    assert certificate["baseline"]["rank"] == 1
    assert certificate["results"][1]["robust"]
    assert certificate["results"][2]["robust"]
    mixed = certificate["results"][3]
    assert mixed["worst_supported_rank"] == 2
    assert not mixed["robust"] and not mixed["unsupported_attainable"]
    assert mixed["rank_witness"]["focus"]["after"]["score"] == certificate["baseline"]["score"]
    residual = mixed["rank_witness"]["residual_edge_ids"][0]
    assert (
        next(edge for edge in graph["edges"] if edge["id"] == residual)["source"] == "Compound::0"
    )
    assert auditor.verify(certificate)["valid"]


def test_pubmed_scope_is_explicit_and_replayable(tmp_path):
    graph = _grouped_graph(0)
    auditor = MixedAuditor(create_fixture_engine(tmp_path, graph))
    groups = sorted(_literal_groups(graph, "pubmed"))
    cert = auditor.audit("Disease::0", "Compound::0", group_kind="pubmed", group_ids=groups)
    assert auditor.verify(cert)["valid"]
    with pytest.raises(ValueError, match="explicit"):
        auditor.audit("Disease::0", "Compound::0", group_kind="pubmed")


def test_empty_binding_catalogue_and_missing_annotations_are_well_defined(tmp_path):
    graph = tiny_graph()
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "BINDS"]
    auditor = MixedAuditor(create_fixture_engine(tmp_path, graph))
    cert = auditor.audit("Disease::D1", "Compound::C2")
    assert cert["scope"]["group_ids"] == []
    assert cert["proof"]["conditional_slice_count"] == 1
    assert cert["results"][-1]["unsupported_attainable"]
    assert cert["results"][-1]["worst_supported_rank"] is None
    assert auditor.baseline_candidates("Disease::D1") == []
    assert auditor.verify(cert)["valid"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("top_k", True),
        ("top_k", 0),
        ("top_k", 101),
        ("group_budget", 2),
        ("group_budget", 1.0),
        ("edge_budget", -1),
        ("edge_budget", False),
        ("group_kind", "retraction"),
        ("group_ids", []),
        ("group_ids", "source:x"),
        ("group_ids", ["source:x"]),
        ("group_ids", [1]),
        ("group_ids", ["x"] * 17),
    ],
)
def test_invalid_unbounded_or_ambiguous_scopes_fail_closed(tmp_path, name, value):
    auditor = MixedAuditor(create_fixture_engine(tmp_path))
    with pytest.raises(ValueError):
        auditor.audit("Disease::D1", "Compound::C2", **{name: value})


@pytest.mark.parametrize(
    "mutation",
    [
        "rank",
        "support",
        "scorer",
        "method",
        "schema",
        "scope",
        "model",
        "extra",
        "witness",
        "hash",
        "size",
        "nan",
    ],
)
def test_forged_even_correctly_rehashed_certificates_are_rejected(tmp_path, mutation):
    auditor = MixedAuditor(create_fixture_engine(tmp_path, _grouped_graph(2)))
    cert = auditor.audit("Disease::0", "Compound::0")
    if mutation == "rank":
        cert["results"][0]["worst_supported_rank"] = 888
    elif mutation == "support":
        cert["results"][-1]["unsupported_attainable"] = not cert["results"][-1][
            "unsupported_attainable"
        ]
    elif mutation == "scorer":
        cert["identity"]["scorer"] = "float64-fixed-order-v1"
    elif mutation == "method":
        cert["method"] = "not-mixed"
    elif mutation == "schema":
        cert["schema_version"] = "99.0"
    elif mutation == "scope":
        cert["scope"]["group_ids"] = []
    elif mutation == "model":
        cert["identity"]["model_sha256"] = "other"
    elif mutation == "extra":
        cert["future_guarantee"] = True
    elif mutation == "witness":
        for row in cert["results"]:
            witness = row["rank_witness"] or row["unsupported_witness"]
            if witness:
                witness["removed_edge_count"] += 1
                break
    elif mutation == "hash":
        cert["certificate_sha256"] = "0" * 64
    elif mutation == "size":
        cert["padding"] = "a" * (256 * 1024)
    elif mutation == "nan":
        cert["baseline"]["score"] = float("nan")
    if mutation not in ("hash", "nan"):
        cert["certificate_sha256"] = certificate_digest(cert)
    result = auditor.verify(cert)
    assert not result["valid"], mutation
    assert result["errors"]


def test_external_mutation_cache_eviction_and_concurrency_do_not_change_seals(tmp_path):
    engine = create_fixture_engine(tmp_path, _grouped_graph(2))
    auditor = MixedAuditor(engine, cache_size=1)
    original = auditor.audit("Disease::0", "Compound::0")
    before = deepcopy(original)
    engine.nodes["Compound::0"]["name"] = "changed"
    engine.model["intercept"] = 99
    engine.path_counts[:] = 0
    engine.matrices["BINDS"].data[:] = 0
    auditor.audit("Disease::1", "Compound::1")
    original["scope"]["groups"][0]["label"] = "response mutated"
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: auditor.audit("Disease::0", "Compound::0"), range(6)))
    assert all(result == before for result in results)
    assert auditor.verify(before)["valid"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("scale", [0] * 8),
        ("coefficients", [float("nan")] * 8),
        ("intercept", float("inf")),
        ("model_sha256", "bad"),
    ],
)
def test_invalid_fitted_model_cannot_create_mixed_certificate(tmp_path, name, value):
    engine = create_fixture_engine(tmp_path)
    engine.model[name] = value
    with pytest.raises(ValueError):
        MixedAuditor(engine)


def test_json_roundtrip_and_unknown_input_types(tmp_path):
    auditor = MixedAuditor(create_fixture_engine(tmp_path))
    certificate = json.loads(json.dumps(auditor.audit("Disease::D1", "Compound::C2")))
    assert auditor.verify(certificate)["valid"]
    for invalid in (None, [], "certificate", {}, {"method": METHOD}):
        assert not auditor.verify(invalid)["valid"]
    with pytest.raises(KeyError):
        auditor.audit("Gene::G1", "Compound::C2")
    with pytest.raises(KeyError):
        auditor.audit("Disease::D1", "Gene::G1")
    with pytest.raises(KeyError):
        auditor.baseline_candidates("missing")
    for groups, edges in ((["x"], []), ([], ["x"]), ([1], []), ([], ["e0", "e2"]), ("x", [])):
        with pytest.raises(ValueError):
            auditor.replay("Disease::D1", "Compound::C2", groups, edges)
