"""Hand-checkable graph invariants and evidence-sensitivity behavior."""

import copy
import json

import numpy as np
import pytest

from app.graph_engine import GraphEngine, validate_exclusions


def tiny_graph():
    """A graph whose complete simple paths can be counted manually.

    C1 binds G1, C2 binds G2, C3 binds G3; G1--G2--G3.
    D1 associates G1 and G3; D2 associates G2. Every gene participates in P1.
    C0 has no targets. This exposes repeated-gene pathway counting mistakes.
    """
    nodes = []
    for label, identifiers in {
        "Compound": ("C0", "C1", "C2", "C3"),
        "Gene": ("G1", "G2", "G3"),
        "Disease": ("D1", "D2"),
        "Pathway": ("P1",),
    }.items():
        nodes.extend(
            {
                "id": f"{label}::{identifier}",
                "identifier": identifier,
                "name": identifier,
                "label": label,
                "url": f"https://example.org/{identifier}",
                "data": {},
            }
            for identifier in identifiers
        )
    edges = []

    def edge(left, relation, right):
        edges.append(
            {
                "id": f"e{len(edges)}",
                "source": left,
                "target": right,
                "type": relation,
                "sources": ["Hand-counted fixture"],
                "license": "CC0",
                "data": {"source": "Hand-counted fixture"},
            }
        )

    for number in (1, 2, 3):
        edge(f"Compound::C{number}", "BINDS", f"Gene::G{number}")
        edge(f"Gene::G{number}", "PARTICIPATES", "Pathway::P1")
    edge("Gene::G1", "INTERACTS", "Gene::G2")
    edge("Gene::G2", "INTERACTS", "Gene::G3")
    edge("Disease::D1", "ASSOCIATES", "Gene::G1")
    edge("Disease::D1", "ASSOCIATES", "Gene::G3")
    edge("Disease::D2", "ASSOCIATES", "Gene::G2")
    return {
        "nodes": nodes,
        "edges": edges,
        "treatments": [{"source": "Compound::C1", "target": "Disease::D1"}],
        "metadata": {"dataset": "Hand-counted test fixture", "dataset_sha256": "fixture"},
    }


def create_fixture_engine(tmp_path, graph=None):
    """Create an explicit small model, independent of training implementation."""
    graph = tiny_graph() if graph is None else graph
    (tmp_path / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    model = {
        "name": "Fixture coefficients",
        "mean": [0] * 8,
        "scale": [1] * 8,
        "coefficients": [0.8, 2.0, 0.1, 0, 0, 0, 0, 0],
        "intercept": 0.0,
    }
    (tmp_path / "model.json").write_text(json.dumps(model), encoding="utf-8")
    (tmp_path / "evaluation.json").write_text('{"executed":true}', encoding="utf-8")
    return GraphEngine(tmp_path)


@pytest.fixture
def engine(tmp_path):
    """Provide a manually tractable graph to each test."""
    return create_fixture_engine(tmp_path)


def test_simple_path_counts_are_hand_checkable(engine):
    """A pathway with the same gene twice must never inflate evidence counts."""
    expected = {
        ("C1", "D1"): (1, 0, 1),
        ("C2", "D1"): (0, 2, 2),
        ("C3", "D1"): (1, 0, 1),
        ("C1", "D2"): (0, 1, 1),
        ("C2", "D2"): (1, 0, 0),
        ("C3", "D2"): (0, 1, 1),
    }
    for (compound, disease), counts in expected.items():
        evidence = engine.evidence(f"Disease::{disease}", f"Compound::{compound}", limit=100)
        assert tuple(evidence["counts"].values()) == counts
        assert len(evidence["paths"]) == sum(counts)
        assert not evidence["truncated"]
        for path in evidence["paths"]:
            assert len(path["node_ids"]) == len(set(path["node_ids"]))
            assert len(path["edge_ids"]) == len(path["node_ids"]) - 1


def test_display_truncation_never_changes_feature_counts(engine):
    """A bounded graph display must still disclose the exact full path total."""
    evidence = engine.evidence("Disease::D1", "Compound::C2", limit=1)
    assert len(evidence["paths"]) == 1
    assert evidence["total_paths"] == 4
    assert evidence["counts"] == {"direct": 0, "interaction": 2, "pathway": 2}
    assert evidence["truncated"] is True


@pytest.mark.parametrize(
    "excluded", [("INTERACTS",), ("PARTICIPATES",), ("INTERACTS", "PARTICIPATES")]
)
def test_ablated_paths_never_include_removed_families(engine, excluded):
    """The explanation graph and its exact feature counts describe the same ablation."""
    evidence = engine.evidence("Disease::D1", "Compound::C2", exclude=excluded, limit=100)
    assert not {edge["type"] for edge in evidence["edges"]}.intersection(excluded)
    assert evidence["total_paths"] == len(evidence["paths"])
    if "INTERACTS" in excluded:
        assert evidence["counts"]["interaction"] == 0
    if "PARTICIPATES" in excluded:
        assert evidence["counts"]["pathway"] == 0


@pytest.mark.parametrize("family", ["BINDS", "ASSOCIATES"])
def test_removing_required_evidence_returns_no_supported_candidates(engine, family):
    """An intercept-only model cannot masquerade as evidence-supported recommendations."""
    result = engine.rankings("Disease::D1", exclude=[family])
    assert result["candidates"] == []
    assert result["total"] == 0
    assert engine.evidence("Disease::D1", "Compound::C2", exclude=[family])["total_paths"] == 0


def test_ablation_holds_model_fixed_and_changes_rank(engine):
    """The known graph topology implies C2 loses its rank after interactions vanish."""
    before_model = copy.deepcopy(engine.model)
    result = engine.challenge("Disease::D1", ["INTERACTS"], limit=3)
    assert result["before"][0]["id"] == "Compound::C2"
    assert result["after"][0]["id"] == "Compound::C1"
    changed = next(row for row in result["changes"] if row["id"] == "Compound::C2")
    assert (changed["before_rank"], changed["after_rank"], changed["rank_delta"]) == (1, 3, -2)
    assert engine.model == before_model


def test_treatment_labels_do_not_change_features_or_scores(tmp_path):
    """Changing every recorded indication cannot alter the evidence inference graph."""
    graph = tiny_graph()
    first = create_fixture_engine(tmp_path, graph)
    graph["treatments"] = [{"source": "Compound::C3", "target": "Disease::D2"}]
    second = create_fixture_engine(tmp_path, graph)
    np.testing.assert_array_equal(first.feature_matrix(), second.feature_matrix())
    first_rows = first.rankings("Disease::D1")["candidates"]
    second_rows = second.rankings("Disease::D1")["candidates"]
    assert [(row["id"], row["score"]) for row in first_rows] == [
        (row["id"], row["score"]) for row in second_rows
    ]
    assert any(row["known_treatment"] for row in first_rows)
    assert not any(row["known_treatment"] for row in second_rows)


def test_label_edges_in_evidence_are_rejected(tmp_path):
    """Fail closed if an import accidentally puts an indication into the evidence graph."""
    graph = tiny_graph()
    graph["edges"].append(
        {"id": "leak", "source": "Compound::C1", "target": "Disease::D1", "type": "TREATS"}
    )
    with pytest.raises(ValueError, match="leakage"):
        create_fixture_engine(tmp_path, graph)


def test_unknown_exclusions_and_identifiers_are_not_silently_ignored(engine):
    """Invalid user selections cannot appear to execute successfully."""
    with pytest.raises(ValueError, match="Unknown evidence"):
        engine.rankings("Disease::D1", exclude=["TREATS"])
    with pytest.raises(KeyError, match="Unknown disease"):
        engine.rankings("Disease::DOID:absent")
    with pytest.raises(KeyError, match="Unknown compound"):
        engine.evidence("Disease::D1", "Gene::G1")


@pytest.mark.parametrize(
    "method,args",
    [
        ("evidence", ("Disease::D1", "Compound::C1")),
        ("rankings", ("Disease::D1",)),
        ("similar", ("Compound::C1",)),
        ("algorithms", ("Disease::D1",)),
        ("diseases", ()),
    ],
)
def test_unbounded_or_invalid_limits_are_rejected(engine, method, args):
    """Each expensive API-facing operation enforces its own bounds."""
    with pytest.raises(ValueError):
        getattr(engine, method)(*args, limit=0)
    with pytest.raises(ValueError):
        getattr(engine, method)(*args, limit=10000)


def test_rankings_are_stable_and_do_not_include_isolated_compounds(engine):
    """Unsupported compounds remain absent and ties have deterministic IDs."""
    result = engine.rankings("Disease::D1")
    assert [row["id"] for row in result["candidates"]] == [
        "Compound::C2",
        "Compound::C1",
        "Compound::C3",
    ]
    assert (
        engine.rankings("Disease::D1", limit=1, offset=1)["candidates"][0]["id"] == "Compound::C1"
    )


def test_provenance_survives_evidence_selection(engine):
    """Returned paths retain exact edge source and license metadata."""
    result = engine.evidence("Disease::D1", "Compound::C1")
    assert all(edge["sources"] == ["Hand-counted fixture"] for edge in result["edges"])
    assert all(edge["license"] == "CC0" for edge in result["edges"])
    assert all(node["url"].startswith("https://example.org/") for node in result["nodes"])


def test_similarity_uses_shared_targets_not_graph_hubs(engine):
    """Distinct targets give zero Jaccard even when genes share a pathway."""
    assert engine.similar("Compound::C1")["items"] == []
    assert engine.similar("Compound::C0")["items"] == []


def test_personalized_pagerank_is_finite_and_explicit_about_backend(engine):
    """A dangling node cannot create NaN scores or a false claim of GDS execution."""
    result = engine.algorithms("Disease::D1")
    assert result["execution_backend"] == "scipy-power-iteration"
    assert result["converged"]
    assert all(np.isfinite(item["score"]) and item["score"] >= 0 for item in result["items"])
    assert result["items"][-1]["id"] == "Compound::C0"
    assert result["items"][-1]["score"] == 0


def test_artifact_and_search_behaviors(engine):
    """Metadata and case-insensitive search keep stable counts and IDs."""
    assert engine.diseases("d1")["items"] == [{"id": "Disease::D1", "name": "D1"}]
    assert engine.stats()["compounds"] == 4
    assert engine.provenance()["dataset_sha256"] == "fixture"
    assert engine.evaluation() == {"executed": True}
    assert validate_exclusions("INTERACTS,PARTICIPATES,INTERACTS") == ("INTERACTS", "PARTICIPATES")


def test_missing_artifacts_fail_with_actionable_errors(tmp_path):
    """Never silently replace an unexecuted model or experiment with demo values."""
    with pytest.raises(FileNotFoundError, match="prepare_data"):
        GraphEngine(tmp_path)
    create_fixture_engine(tmp_path)
    (tmp_path / "model.json").unlink()
    (tmp_path / "evaluation.json").unlink()
    unloaded = GraphEngine(tmp_path)
    with pytest.raises(RuntimeError, match="evaluate"):
        unloaded.rankings("Disease::D1")
    with pytest.raises(FileNotFoundError, match="evaluate"):
        unloaded.evaluation()


def test_public_score_matrix_cannot_mutate_cached_inference(engine):
    """A benchmark consumer cannot overwrite scores used by future requests."""
    first = engine.score_matrix()
    original = first.copy()
    first[:] = -100
    np.testing.assert_array_equal(engine.score_matrix(), original)


@pytest.mark.parametrize(
    "change,message",
    [
        ({"dataset_sha256": "different"}, "different dataset"),
        ({"feature_names": ["leaky_treatment_edge"]}, "feature definitions"),
        ({"model_sha256": "bad"}, "Model checksum"),
    ],
)
def test_mismatched_model_artifacts_fail_closed(tmp_path, change, message):
    """Changing model identity or features cannot silently serve invalid scores."""
    create_fixture_engine(tmp_path)
    model_path = tmp_path / "model.json"
    model = json.loads(model_path.read_text())
    model.update(change)
    model_path.write_text(json.dumps(model))
    with pytest.raises(ValueError, match=message):
        GraphEngine(tmp_path)


def test_corrupt_processed_graph_is_detected(tmp_path):
    """The source dataset checksum alone cannot mask a changed processed graph."""
    create_fixture_engine(tmp_path)
    (tmp_path / "manifest.json").write_text(json.dumps({"graph_sha256": "bad"}))
    with pytest.raises(ValueError, match="Processed graph checksum"):
        GraphEngine(tmp_path)
