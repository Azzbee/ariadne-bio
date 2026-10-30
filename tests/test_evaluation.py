"""Tests of experimental separation, retrieval metrics and source integrity."""

import hashlib
import bz2
import io
import json
from pathlib import Path

import numpy as np
import pytest

from scripts import prepare_data
from scripts.evaluate import (
    cluster_bootstrap,
    retrieval_metrics,
    run_evaluation,
    sample_unobserved,
    split_pairs,
)
from scripts.prepare_data import EXPECTED_SHA256, normalize_edge, prepare, sources_for
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def test_split_is_disjoint_complete_and_reproducible():
    """Every positive belongs to one split and input ordering cannot change it."""
    pairs = [(f"C{index}", f"D{index % 7}") for index in range(100)]
    first = split_pairs(pairs, 42)
    second = split_pairs(list(reversed(pairs)), 42)
    assert first == second
    assert {key: len(value) for key, value in first.items()} == {
        "train": 70,
        "validation": 15,
        "test": 15,
    }
    assert set(first["train"]).isdisjoint(first["validation"])
    assert set(first["train"]).isdisjoint(first["test"])
    assert set(first["validation"]).isdisjoint(first["test"])
    assert set().union(*map(set, first.values())) == set(pairs)
    assert first != split_pairs(pairs, 43)


def test_training_unobserved_sampler_never_samples_a_known_positive(tmp_path):
    """No known held-out indication can be mislabeled as an observed negative."""
    engine = create_fixture_engine(tmp_path)
    training = [("Compound::C1", "Disease::D1")]
    sampled = sample_unobserved(engine, training, seed=42)
    assert set(sampled).isdisjoint(engine.known_treatments)
    assert len(sampled) == len(set(sampled)) == 3
    assert all(disease == "Disease::D1" for _, disease in sampled)
    assert sampled == sample_unobserved(engine, training, seed=42)


def test_full_candidate_metrics_include_zero_path_candidates_and_mask_known(tmp_path):
    """Hand-calculated rank verifies masking and reciprocal-rank interpretation."""
    engine = create_fixture_engine(tmp_path)
    # C0=0.9 (isolated), C1=1.0 (masked), C2=0.8, C3=0.7 for disease D1.
    scores = np.array([[0.9, 0.0], [1.0, 0.0], [0.8, 0.0], [0.7, 0.0]])
    metrics, examples = retrieval_metrics(
        engine, scores, [("Compound::C2", "Disease::D1")], [("Compound::C1", "Disease::D1")]
    )
    assert metrics["mrr"] == 0.5
    assert metrics["mean_rank"] == 2.0
    assert examples[0]["candidate_count"] == 3


def test_other_test_positives_remain_candidates_and_ties_use_ids(tmp_path):
    """Evaluation does not make retrieval artificially easier by filtering test truths."""
    engine = create_fixture_engine(tmp_path)
    metrics, examples = retrieval_metrics(
        engine,
        np.ones((4, 2)),
        [("Compound::C1", "Disease::D1"), ("Compound::C2", "Disease::D1")],
        [],
    )
    assert [example["rank"] for example in examples] == [2, 3]
    assert metrics["mrr"] == pytest.approx((0.5 + 1 / 3) / 2)


def test_corrupted_download_is_refused_before_writing_processed_files(tmp_path):
    """A wrong or LFS-pointer payload cannot masquerade as the pinned dataset."""
    raw = tmp_path / "bad.json.bz2"
    raw.write_bytes(b"version https://git-lfs.github.com/spec/v1")
    target = tmp_path / "processed"
    with pytest.raises(ValueError, match="checksum mismatch"):
        prepare(raw, target)
    assert not target.exists()


def test_upstream_metadata_is_retained_without_inventing_provenance():
    """Missing license stays missing and database source names are not paper citations."""
    source = {
        "source_id": ["Compound", "DB1"],
        "target_id": ["Gene", 1],
        "kind": "binds",
        "direction": "both",
        "data": {"sources": ["Database B", "Database A"]},
    }
    edge = normalize_edge(source, "BINDS")
    assert edge["sources"] == ["Database A", "Database B"]
    assert edge["license"] is None
    assert edge["data"] == source["data"]
    assert edge["id"] == normalize_edge(source, "BINDS")["id"]
    assert edge["source"] == "Compound::DB1"
    assert edge["target"] == "Gene::1"
    assert sources_for({"source": "One database"}) == ["One database"]
    assert sources_for({}) == []


def test_training_and_evaluation_execute_end_to_end_on_explicit_fixture(tmp_path):
    """Exercise fitting, model selection, ablation and serialization without network."""
    graph = tiny_graph()
    graph["treatments"] = [
        {"source": f"Compound::{compound}", "target": f"Disease::{disease}"}
        for compound, disease in [("C1", "D1"), ("C3", "D1"), ("C1", "D2"), ("C2", "D2")]
    ]
    create_fixture_engine(tmp_path, graph)
    report = run_evaluation(tmp_path, seed=42)
    model = json.loads((tmp_path / "model.json").read_text())
    assert model["training_positive_pairs"] == report["split"]["train"] == 2
    assert report["split"]["validation"] == 1
    assert report["split"]["test"] == 1
    assert len(report["metrics"]) == 4
    assert model["fit_scope"].startswith("Training split only")
    assert report["protocol"]["candidate_count"] == 4
    assert report["protocol"]["candidate_universe"].startswith("All 4 compounds")
    assert {row["excluded"][0] for row in report["ablations"]} == {"INTERACTS", "PARTICIPATES"}


def test_cluster_uncertainty_is_reproducible_and_uses_all_links():
    """Bootstrap intervals contain the point estimate for this heterogeneous fixture."""
    ranks = [
        {"disease_id": "D1", "rank": 1},
        {"disease_id": "D1", "rank": 2},
        {"disease_id": "D2", "rank": 100},
    ]
    result = cluster_bootstrap(ranks, seed=42)
    assert result == cluster_bootstrap(ranks, seed=42)
    assert result["recall_at_10_ci95"] == [0.0, 1.0]
    assert result["mrr_ci95"][0] <= (1 + 0.5 + 0.01) / 3 <= result["mrr_ci95"][1]


def test_streaming_preparation_separates_labels_and_retains_properties(tmp_path, monkeypatch):
    """A tiny upstream-format payload tests streaming extraction and idempotence."""
    nodes = [
        {
            "kind": label,
            "identifier": identifier,
            "name": identifier,
            "data": {"source": "Fixture", "license": "CC0"},
        }
        for label, identifier in [
            ("Compound", "C1"),
            ("Gene", "G1"),
            ("Disease", "D1"),
            ("Pathway", "P1"),
            ("Side Effect", "S1"),
        ]
    ]
    edges = [
        {
            "source_id": left,
            "target_id": right,
            "kind": kind,
            "direction": "both",
            "data": {"source": "Fixture", "value": 0.25},
        }
        for left, kind, right in [
            (["Compound", "C1"], "binds", ["Gene", "G1"]),
            (["Disease", "D1"], "associates", ["Gene", "G1"]),
            (["Gene", "G1"], "participates", ["Pathway", "P1"]),
            (["Gene", "G1"], "interacts", ["Gene", "G1"]),
            (["Compound", "C1"], "treats", ["Disease", "D1"]),
            (["Compound", "C1"], "palliates", ["Disease", "D1"]),
        ]
    ]
    raw = tmp_path / "tiny.json.bz2"
    raw.write_bytes(bz2.compress(json.dumps({"nodes": nodes, "edges": edges}).encode()))
    monkeypatch.setattr(
        prepare_data, "EXPECTED_SHA256", hashlib.sha256(raw.read_bytes()).hexdigest()
    )
    monkeypatch.setattr(prepare_data, "EXPECTED_NODE_COUNT", 4)
    monkeypatch.setattr(prepare_data, "EXPECTED_TREATMENT_COUNT", 1)
    destination = tmp_path / "processed"
    first = prepare(raw, destination)
    second = prepare(raw, destination)
    assert first == second
    graph = json.loads((destination / "graph.json").read_text())
    assert len(graph["nodes"]) == 4
    assert {edge["type"] for edge in graph["edges"]} == {"BINDS", "ASSOCIATES", "PARTICIPATES"}
    assert len(graph["treatments"]) == 1
    assert first["discarded_self_loops"] == 1
    assert all(edge["data"]["value"] == 0.25 for edge in graph["edges"])


def test_download_is_atomic_and_cleans_failed_payloads(tmp_path, monkeypatch):
    """Network failure or a mismatched checksum must not leave a usable bad dataset."""
    payload = b"test payload"
    destination = tmp_path / "raw" / "test.bz2"
    monkeypatch.setattr(
        prepare_data.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(payload)
    )
    with pytest.raises(ValueError, match="checksum"):
        prepare_data.download_dataset(destination)
    assert not destination.exists()
    assert not destination.with_suffix(".bz2.part").exists()
    monkeypatch.setattr(prepare_data, "EXPECTED_SHA256", hashlib.sha256(payload).hexdigest())
    prepare_data.download_dataset(destination)
    assert destination.read_bytes() == payload


@pytest.mark.skipif(
    not Path("data/processed/evaluation.json").exists(),
    reason="Full dataset artifacts not prepared",
)
def test_executed_report_retains_every_test_failure_and_positive():
    """The published metrics must agree with all retained test ranks."""
    report = json.loads(Path("data/processed/evaluation.json").read_text(encoding="utf-8"))
    assert report["dataset_sha256"] == EXPECTED_SHA256
    pairs = report["split"]["pair_ids"]
    assert len(pairs["test"]) == report["split"]["test"] == 114
    for metric in report["metrics"]:
        ranks = report["test_ranks"][metric["model"]]
        assert len(ranks) == 114
        assert metric["hits_at_10"] == sum(row["rank"] <= 10 for row in ranks)
        assert metric["mrr"] == pytest.approx(np.mean([1 / row["rank"] for row in ranks]))
    model = json.loads(Path("data/processed/model.json").read_text(encoding="utf-8"))
    stored_hash = model.pop("model_sha256")
    assert hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest() == stored_hash
