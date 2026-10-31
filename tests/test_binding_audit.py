"""Independent global enumeration, numerical semantics and adversarial certificates."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import itertools
import json
import math
from pathlib import Path
import subprocess

import numpy as np
import pytest
from scipy.special import expit

from app.binding_audit import BindingAuditor, canonical_scores, certificate_digest
from app.graph_engine import GraphEngine
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def _make_graph(seed=0):
    """Generate small typed graphs with independently countable simple paths."""
    rng = np.random.default_rng(seed)
    graph = {"nodes": [], "edges": [], "treatments": [], "metadata": {"dataset": "oracle"}}
    labels = {"Compound": 4, "Gene": 4, "Disease": 2, "Pathway": 2}
    for label, count in labels.items():
        for number in range(count):
            identifier = f"{label}::{number}"
            graph["nodes"].append({"id": identifier, "name": identifier, "label": label})

    def append(left, kind, right):
        graph["edges"].append(
            {
                "id": f"edge-{len(graph['edges']):03d}",
                "source": left,
                "target": right,
                "type": kind,
                "sources": ["Synthetic oracle"],
                "license": None,
                "data": {},
            }
        )

    for compound, gene in itertools.product(range(4), repeat=2):
        if rng.random() < 0.45:
            append(f"Compound::{compound}", "BINDS", f"Gene::{gene}")
    for left, right in itertools.combinations(range(4), 2):
        if rng.random() < 0.65:
            append(f"Gene::{left}", "INTERACTS", f"Gene::{right}")
    for gene, pathway in itertools.product(range(4), range(2)):
        if rng.random() < 0.65:
            append(f"Gene::{gene}", "PARTICIPATES", f"Pathway::{pathway}")
    for disease, gene in itertools.product(range(2), range(4)):
        if rng.random() < 0.65:
            append(f"Disease::{disease}", "ASSOCIATES", f"Gene::{gene}")
    return graph


def _oracle(graph, model, disease, removed):
    """Enumerate literal paths and rank using an independent scalar calculation."""
    edges = [edge for edge in graph["edges"] if edge["id"] not in removed]
    compounds = sorted(node["id"] for node in graph["nodes"] if node["label"] == "Compound")
    associations = {
        edge["target"]
        for edge in edges
        if edge["type"] == "ASSOCIATES" and edge["source"] == disease
    }
    interactions = {
        frozenset((edge["source"], edge["target"])) for edge in edges if edge["type"] == "INTERACTS"
    }
    participation = {
        (edge["source"], edge["target"]) for edge in edges if edge["type"] == "PARTICIPATES"
    }
    pathways = [node["id"] for node in graph["nodes"] if node["label"] == "Pathway"]
    states = {}
    for compound in compounds:
        targets = {
            edge["target"]
            for edge in edges
            if edge["type"] == "BINDS" and edge["source"] == compound
        }
        direct = len(targets & associations)
        interaction = sum(
            left != right and frozenset((left, right)) in interactions
            for left, right in itertools.product(targets, associations)
        )
        pathway = sum(
            left != right and (left, middle) in participation and (right, middle) in participation
            for left, right, middle in itertools.product(targets, associations, pathways)
        )
        counts = np.asarray([direct, interaction, pathway], dtype=np.float64)
        divisor = np.sqrt(np.float64(max(len(targets) * len(associations), 1)))
        features = [np.log1p(count) for count in counts]
        features.extend(np.log1p(count / divisor) for count in counts)
        features.extend(
            (np.log1p(np.float64(len(targets))), np.log1p(np.float64(len(associations))))
        )
        logit = np.float64(model["intercept"])
        for index in range(8):
            term = np.float64(model["coefficients"][index]) * (
                (features[index] - np.float64(model["mean"][index]))
                / np.float64(model["scale"][index])
            )
            logit = np.float64(logit + term)
        states[compound] = {
            "supported": bool(sum(counts)),
            "rank": None,
            "score": float(expit(logit)),
            "logit": float(logit),
            "counts": dict(zip(("direct", "interaction", "pathway"), map(int, counts))),
            "evidence_count": int(sum(counts)),
        }
    supported = sorted(
        (key for key in compounds if states[key]["supported"]),
        key=lambda key: (-states[key]["score"], key),
    )
    for rank, compound in enumerate(supported, 1):
        states[compound]["rank"] = rank
    return states


@pytest.mark.parametrize("seed", range(8))
def test_all_global_subsets_match_independent_literal_path_oracle(tmp_path, seed):
    """Compare maxima, infeasibility, minimum budgets and witnesses, not just scores."""
    graph = _make_graph(seed)
    engine = create_fixture_engine(tmp_path, graph)
    rng = np.random.default_rng(seed + 50)
    engine.model.update(
        coefficients=rng.uniform(-3, 3, 8).tolist(),
        mean=rng.uniform(-1, 1, 8).tolist(),
        scale=rng.uniform(0.2, 2, 8).tolist(),
        intercept=float(rng.normal()),
    )
    auditor = BindingAuditor(engine)
    binding_ids = sorted(edge["id"] for edge in graph["edges"] if edge["type"] == "BINDS")
    for disease in engine.entities["Disease"]:
        worlds = [
            (removed, _oracle(graph, engine.model, disease, removed))
            for size in range(3)
            for removed in itertools.combinations(binding_ids, size)
        ]
        for compound in engine.entities["Compound"]:
            certificate = auditor.audit(disease, compound, top_k=2)
            baseline = worlds[0][1][compound]
            assert {key: certificate["baseline"][key] for key in baseline} == baseline
            local_ids = {
                edge["id"]
                for edge in graph["edges"]
                if edge["type"] == "BINDS" and edge["source"] == compound
            }
            first_failure = None
            for result in certificate["results"]:
                subset = [
                    (deleted, states[compound])
                    for deleted, states in worlds
                    if len(deleted) <= result["budget"]
                ]
                supported = [state["rank"] for _, state in subset if state["supported"]]
                local = [
                    state["rank"]
                    for deleted, state in subset
                    if state["supported"] and set(deleted) <= local_ids
                ]
                absent = any(not state["supported"] for _, state in subset)
                assert result["worst_supported_rank"] == (max(supported) if supported else None)
                assert result["focus_only_worst_rank"] == (max(local) if local else None)
                assert result["unsupported_attainable"] == absent
                robust = not absent and bool(supported) and max(supported) <= 2
                assert result["top_k_robust"] == robust
                if first_failure is None and not robust:
                    first_failure = result["budget"]
                for key in ("rank_witness", "unsupported_witness"):
                    witness = result[key]
                    if witness is None:
                        continue
                    assert len(witness["removed_edge_ids"]) <= result["budget"]
                    expected = _oracle(graph, engine.model, disease, witness["removed_edge_ids"])[
                        compound
                    ]
                    assert witness["focus"] == expected
                    assert (
                        auditor.replay(disease, compound, witness["removed_edge_ids"])["focus"]
                        == expected
                    )
            assert certificate["minimum_failure_budget"] == first_failure
            assert auditor.verify(certificate)["valid"]


def test_competitor_promotions_expose_optimistic_focus_only_bounds(tmp_path):
    """Two rivals can each spend one deletion to outrank an unchanged focus."""
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
                    "sources": ["fixture"],
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
        for gene in [1, 2]
    )
    engine = create_fixture_engine(tmp_path, graph)
    engine.model["coefficients"] = [0, 0, 0, 0, 0, 0, -1, 0]
    auditor = BindingAuditor(engine)
    certificate = auditor.audit("Disease::0", "Compound::2", top_k=1)
    assert certificate["baseline"]["rank"] == 1
    assert [row["worst_supported_rank"] for row in certificate["results"]] == [1, 2, 3]
    assert [row["focus_only_worst_rank"] for row in certificate["results"]] == [1, 1, 1]
    assert certificate["results"][1]["unsupported_attainable"] is False
    assert certificate["minimum_failure_budget"] == 1
    witness = certificate["results"][2]["rank_witness"]
    assert witness["removed_edge_ids"] == ["b0-0", "b1-0"]
    assert all(row["role"] == "competitor" for row in witness["changed_compounds"])
    assert witness["focus"]["score"] == certificate["baseline"]["score"]
    assert auditor.verify(certificate)["valid"]


def test_canonical_scores_are_bitwise_identical_across_batch_shapes():
    """An asymmetric model catches reduction-order and sigmoid-tie shortcuts."""
    model = {
        "coefficients": [0.32, 0.88, 4.02, 0.31, -0.34, -2.66, -0.81, -1.37],
        "mean": [0.2] * 8,
        "scale": [0.5, 1.1, 2.3, 0.02, 0.16, 1.16, 0.95, 1.03],
        "intercept": -0.59,
    }
    counts = np.array([[6, 11, 1237], [0, 0, 0], [0, 4000, 2], [2, 0, 5]])
    degrees = np.array([21, 0, 8, 132])
    batch = canonical_scores(counts, degrees, 196, model)
    scalar = [canonical_scores(row, degrees[index], 196, model) for index, row in enumerate(counts)]
    np.testing.assert_array_equal(batch[0], [item[0] for item in scalar])
    np.testing.assert_array_equal(batch[1], [item[1] for item in scalar])
    reshaped = canonical_scores(counts.reshape(2, 2, 3), degrees.reshape(2, 2), 196, model)
    np.testing.assert_array_equal(batch[0], reshaped[0].ravel())
    np.testing.assert_array_equal(batch[1], reshaped[1].ravel())


def test_sigmoid_saturation_ties_use_id_not_logit(tmp_path):
    engine = create_fixture_engine(tmp_path)
    engine.model["intercept"] = 1000
    certificate = BindingAuditor(engine).audit("Disease::D1", "Compound::C2", top_k=1)
    assert certificate["baseline"]["score"] == 1
    assert certificate["baseline"]["rank"] == 2
    assert certificate["minimum_failure_budget"] == 0


def test_isolated_pair_and_empty_disease_never_get_a_supported_rank(tmp_path):
    graph = tiny_graph()
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "ASSOCIATES"]
    auditor = BindingAuditor(create_fixture_engine(tmp_path, graph))
    certificate = auditor.audit("Disease::D1", "Compound::C0")
    assert certificate["baseline"]["supported"] is False
    assert certificate["minimum_failure_budget"] == 0
    assert certificate["robust_through_budget"] is None
    for result in certificate["results"]:
        assert result["worst_supported_rank"] is None
        assert result["rank_witness"] is None
        assert result["unsupported_attainable"]
        assert math.isfinite(result["unsupported_witness"]["focus"]["score"])
    assert auditor.verify(certificate)["valid"]


@pytest.mark.parametrize("duplicate_id", [True, False])
def test_duplicate_binding_records_are_rejected_before_binary_collapse(tmp_path, duplicate_id):
    graph = tiny_graph()
    duplicate = deepcopy(graph["edges"][0])
    if not duplicate_id:
        duplicate["id"] = "different-id-same-endpoints"
    graph["edges"].append(duplicate)
    engine = create_fixture_engine(tmp_path, graph)
    with pytest.raises(ValueError, match="Duplicate"):
        BindingAuditor(engine)


@pytest.mark.parametrize(
    "field,value",
    [
        ("mean", [0] * 7),
        ("scale", [0] * 8),
        ("scale", [float("nan")] * 8),
        ("coefficients", [float("inf")] * 8),
        ("intercept", float("nan")),
        ("feature_names", ["unknown"] * 8),
    ],
)
def test_invalid_model_cannot_receive_a_certificate(tmp_path, field, value):
    engine = create_fixture_engine(tmp_path)
    engine.model[field] = value
    with pytest.raises(ValueError, match="model"):
        BindingAuditor(engine)


def test_missing_model_has_explicit_untrained_error(tmp_path):
    engine = create_fixture_engine(tmp_path)
    engine.model = None
    with pytest.raises(RuntimeError, match="fitted model"):
        BindingAuditor(engine)


@pytest.mark.parametrize(
    "top_k,budget", [(0, 2), (1553, 2), (True, 2), (1, -1), (1, 3), (1, True), (1, 1.0)]
)
def test_request_limits_are_bounded_and_typed(tmp_path, top_k, budget):
    auditor = BindingAuditor(create_fixture_engine(tmp_path))
    with pytest.raises(ValueError, match="Audit"):
        auditor.audit("Disease::D1", "Compound::C1", top_k, budget)


@pytest.mark.parametrize(
    "disease,compound",
    [
        ("Gene::G1", "Compound::C1"),
        ("Disease::D1", "Gene::G1"),
        ("Disease::missing", "Compound::C1"),
    ],
)
def test_invalid_entity_types_are_rejected(tmp_path, disease, compound):
    with pytest.raises(KeyError, match="Unknown"):
        BindingAuditor(create_fixture_engine(tmp_path)).audit(disease, compound)


@pytest.mark.parametrize(
    "removed", [["e0", "e0"], ["e1"], ["missing"], ["e0", "e2", "e4"], "e0", [1]]
)
def test_replay_rejects_invalid_or_out_of_scope_deletions(tmp_path, removed):
    auditor = BindingAuditor(create_fixture_engine(tmp_path))
    with pytest.raises(ValueError):
        auditor.replay("Disease::D1", "Compound::C1", removed)


@pytest.mark.parametrize(
    "field",
    [
        "rank",
        "unsupported",
        "scope",
        "identity",
        "minimum",
        "focus_only",
        "provenance",
        "unknown",
        "missing",
    ],
)
def test_resealed_forged_certificates_fail_full_optimality_verification(tmp_path, field):
    auditor = BindingAuditor(create_fixture_engine(tmp_path))
    certificate = auditor.audit("Disease::D1", "Compound::C2", top_k=1)
    if field == "rank":
        certificate["results"][2]["worst_supported_rank"] = 400
    elif field == "unsupported":
        certificate["results"][2]["unsupported_attainable"] = False
    elif field == "scope":
        certificate["scope"]["eligible_edges"] += 1
    elif field == "identity":
        certificate["identity"]["model_sha256"] = "fake"
    elif field == "minimum":
        certificate["minimum_failure_budget"] = 0
    elif field == "focus_only":
        certificate["results"][1]["focus_only_worst_rank"] = 2
    elif field == "provenance":
        certificate["results"][1]["unsupported_witness"]["removed_records"][0]["sources"] = [
            "invented study"
        ]
    elif field == "unknown":
        certificate["verified"] = True
    else:
        del certificate["proof"]
    certificate["certificate_sha256"] = certificate_digest(certificate)
    result = auditor.verify(certificate)
    assert result["status"] == "invalid"
    assert result["valid"] is False
    assert result["errors"]


@pytest.mark.parametrize(
    "certificate", [None, [], {}, {"score": float("nan")}, {"certificate_sha256": "fake"}]
)
def test_malformed_certificates_return_invalid_instead_of_raising(tmp_path, certificate):
    result = BindingAuditor(create_fixture_engine(tmp_path)).verify(certificate)
    assert result["status"] == "invalid"
    assert result["valid"] is False


def test_cache_is_bounded_thread_safe_and_return_values_cannot_mutate_it(tmp_path):
    engine = create_fixture_engine(tmp_path)
    original = deepcopy(engine.model)
    old_scores = engine.score_matrix()
    auditor = BindingAuditor(engine, cache_size=1)
    with ThreadPoolExecutor(max_workers=4) as pool:
        outputs = list(pool.map(lambda _: auditor.audit("Disease::D1", "Compound::C2"), range(12)))
    assert all(value == outputs[0] for value in outputs)
    preserved = deepcopy(outputs[0])
    outputs[0]["results"][1]["unsupported_witness"]["removed_records"][0]["sources"].append("fake")
    assert auditor.audit("Disease::D1", "Compound::C2") == preserved
    auditor.audit("Disease::D2", "Compound::C2")
    assert len(auditor._cache) == 1
    assert engine.model == original
    np.testing.assert_array_equal(engine.score_matrix(), old_scores)


def test_verification_actually_replays_the_edited_matrices(tmp_path, monkeypatch):
    auditor = BindingAuditor(create_fixture_engine(tmp_path))
    certificate = auditor.audit("Disease::D1", "Compound::C2", top_k=1)

    def incorrect(*_args):
        return {"focus": {"rank": 99}}

    monkeypatch.setattr(auditor, "replay", incorrect)
    result = auditor.verify(certificate)
    assert not result["valid"]
    assert "matrix" in result["errors"][0]


@pytest.mark.parametrize("seed", [2, 5, 9])
def test_global_greedy_baseline_matches_independent_next_edit_search(tmp_path, seed):
    graph = _make_graph(seed)
    engine = create_fixture_engine(tmp_path, graph)
    engine.model["coefficients"] = [0.8, -0.9, 1.2, 2.0, -3.0, 0.4, -1.5, 0.1]
    auditor = BindingAuditor(engine)
    ids = sorted(edge["id"] for edge in graph["edges"] if edge["type"] == "BINDS")
    for compound in engine.entities["Compound"]:
        observed = auditor.greedy("Disease::0", compound)
        removed, best_removed = (), ()
        best = _oracle(graph, engine.model, "Disease::0", removed)[compound]

        def objective(state):
            return len(engine.entities["Compound"]) + 1 if not state["supported"] else state["rank"]

        for result in observed["results"]:
            if result["budget"] and best["supported"]:
                options = []
                for edge_id in ids:
                    if edge_id not in removed:
                        chosen = tuple(sorted((*removed, edge_id)))
                        state = _oracle(graph, engine.model, "Disease::0", chosen)[compound]
                        options.append((objective(state), edge_id, chosen, state))
                if options:
                    option = min(options, key=lambda row: (-row[0], row[1]))
                    removed = option[2]
                    if option[0] > objective(best):
                        best, best_removed = option[3], removed
            assert result["focus"] == best
            assert result["removed_edge_ids"] == list(best_removed)


def test_zero_binding_universe_has_no_candidates_but_finite_diagnostics(tmp_path):
    graph = tiny_graph()
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "BINDS"]
    auditor = BindingAuditor(create_fixture_engine(tmp_path, graph))
    assert auditor.baseline_candidates("Disease::D1") == []
    certificate = auditor.audit("Disease::D1", "Compound::C1")
    assert certificate["proof"]["covered_global_states"] == 1
    assert certificate["proof"]["local_states_evaluated"] == 4
    assert all(row["worst_supported_rank"] is None for row in certificate["results"])
    assert auditor.verify(certificate)["valid"]


@pytest.mark.parametrize("seed", [2, 5, 9])
@pytest.mark.parametrize("top_k", [1, 2, 10])
def test_margin_aware_greedy_matches_full_world_next_edit_oracle(tmp_path, seed, top_k):
    """Rank ties use the actual rival boundary, including changes to competitor rows."""
    graph = _make_graph(seed)
    engine = create_fixture_engine(tmp_path, graph)
    engine.model["coefficients"] = [0.8, -0.9, 1.2, 2.0, -3.0, 0.4, -1.5, 0.1]
    auditor = BindingAuditor(engine)
    ids = sorted(edge["id"] for edge in graph["edges"] if edge["type"] == "BINDS")
    for compound in engine.entities["Compound"]:
        observed = auditor.greedy("Disease::0", compound, score_tiebreak=True, top_k=top_k)
        removed, best_removed = (), ()
        best = _oracle(graph, engine.model, "Disease::0", removed)[compound]

        def objective(state):
            return len(engine.entities["Compound"]) + 1 if not state["supported"] else state["rank"]

        for result in observed["results"]:
            if result["budget"] and best["supported"]:
                options = []
                for edge_id in ids:
                    if edge_id in removed:
                        continue
                    chosen = tuple(sorted((*removed, edge_id)))
                    world = _oracle(graph, engine.model, "Disease::0", chosen)
                    state = world[compound]
                    rival_scores = sorted(
                        [
                            row["score"]
                            for key, row in world.items()
                            if key != compound and row["supported"]
                        ],
                        reverse=True,
                    )
                    threshold = rival_scores[top_k - 1] if len(rival_scores) >= top_k else -math.inf
                    key = (-objective(state), state["score"] - threshold, state["score"], edge_id)
                    options.append((key, chosen, state))
                if options:
                    option = min(options, key=lambda row: row[0])
                    removed = option[1]
                    if objective(option[2]) > objective(best):
                        best, best_removed = option[2], removed
            assert result["focus"] == best
            assert result["removed_edge_ids"] == list(best_removed)


def test_binding_matrix_and_raw_records_must_describe_the_same_graph(tmp_path):
    engine = create_fixture_engine(tmp_path)
    engine.matrices["BINDS"] = engine.matrices["BINDS"].tolil()
    engine.matrices["BINDS"][1, 0] = 0
    engine.matrices["BINDS"][1, 1] = 1
    engine.matrices["BINDS"] = engine.matrices["BINDS"].tocsr()
    with pytest.raises(ValueError, match="endpoints"):
        BindingAuditor(engine)


def _node_roundtrip(value):
    """Exercise JavaScript's actual JSON parser/serializer, not an imitation."""
    program = (
        "let input='';process.stdin.on('data',x=>input+=x);"
        "process.stdin.on('end',()=>process.stdout.write(JSON.stringify(JSON.parse(input))));"
    )
    return json.loads(
        subprocess.check_output(["node", "-e", program], input=json.dumps(value), text=True)
    )


def test_certificate_survives_browser_json_numeric_roundtrip_with_provenance(tmp_path):
    graph = tiny_graph()
    graph["edges"][2]["data"].update(affinity_nM=1e-7, integer_float=12.0, signed_zero=-0.0)
    graph["edges"][2]["sources"] = ["β-Source", "Independent label, not independent study"]
    auditor = BindingAuditor(create_fixture_engine(tmp_path, graph))
    original = auditor.audit("Disease::D1", "Compound::C2", top_k=1)
    transported = _node_roundtrip(original)
    assert type(transported["baseline"]["score_difference"]) is int
    assert type(original["baseline"]["score_difference"]) is float
    assert certificate_digest(original) == certificate_digest(transported)
    assert auditor.verify(transported)["valid"]
    transported["baseline"]["score"] = np.nextafter(transported["baseline"]["score"], 1.0)
    transported["certificate_sha256"] = certificate_digest(transported)
    assert not auditor.verify(transported)["valid"]


@pytest.mark.full_data
@pytest.mark.skipif(
    not Path("data/processed/graph.json").exists(),
    reason="Run make data for real-graph transport evidence",
)
def test_real_hetio_certificate_survives_actual_javascript_roundtrip():
    auditor = BindingAuditor(GraphEngine(Path("data/processed")))
    compound = next(
        identifier
        for identifier in auditor.engine.entities["Compound"]
        if auditor.engine.nodes[identifier]["name"] == "Galantamine"
    )
    certificate = auditor.audit("Disease::DOID:10652", compound)
    transported = _node_roundtrip(certificate)
    assert certificate_digest(transported) == certificate["certificate_sha256"]
    assert auditor.verify(transported)["valid"]
    assert transported["results"][2]["rank_witness"]["removed_records"][0]["sources"]


@pytest.mark.parametrize(
    "number", [2**53, -(2**53), 1e16, 10000000000000000, float("nan"), float("inf")]
)
def test_unsafe_or_nonfinite_json_numbers_are_rejected_before_sealing(number):
    with pytest.raises(ValueError):
        certificate_digest({"nested": [number]})


def test_numeric_encoding_does_not_confuse_booleans_strings_and_numbers():
    assert certificate_digest({"value": 0.0}) == certificate_digest({"value": -0.0})
    assert certificate_digest({"value": -0.0}) == certificate_digest({"value": 0})
    assert len({certificate_digest({"value": value}) for value in [False, 0, "0", None]}) == 4
    assert certificate_digest({"value": 1e-7}) == certificate_digest(
        _node_roundtrip({"value": 1e-7})
    )
