"""Complete-population coverage and fail-closed scientific benchmark checks."""

import hashlib
import json

import pytest

from app.binding_audit import BindingAuditor
from scripts.benchmark_audits import EXAMPLE_FILES, main, run_benchmark
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def test_benchmark_covers_every_supported_candidate_and_budget_on_small_graph(tmp_path):
    report = run_benchmark(create_fixture_engine(tmp_path))
    assert report["status"] == "passed"
    assert report["coverage"] == {
        "diseases_total": 2,
        "diseases_processed": 2,
        "diseases_without_supported_candidates": 0,
        "candidate_queries": 6,
        "budget_results": 18,
        "certificates_verified": 6,
        "certificate_witness_replay_checks": 12,
        "greedy_witness_replay_checks": 12,
        "strong_greedy_witness_replay_checks": 12,
        "failed_checks": 0,
    }
    assert report["summary"][1]["globally_fragile"] == 6
    assert report["summary"][1]["unsupported_attainable"] == 6
    assert report["summary"][1]["greedy_missed_failures"] == 0
    assert report["numerical_comparison"]["legacy_model_and_scorer_changed"] is False
    assert len(report["queries"]) == 6


def test_benchmark_retains_empty_diseases_without_fabricating_candidates(tmp_path):
    graph = tiny_graph()
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "ASSOCIATES"]
    report = run_benchmark(create_fixture_engine(tmp_path, graph))
    assert report["coverage"]["diseases_without_supported_candidates"] == 2
    assert report["coverage"]["candidate_queries"] == 0
    assert report["coverage"]["budget_results"] == 0
    assert report["queries"] == []
    assert report["examples"] == {}
    assert all(row["status"] == "no_supported_candidates" for row in report["diseases"])


def test_benchmark_fails_if_certificate_verification_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(BindingAuditor, "verify", lambda *_: {"valid": False, "errors": ["bad"]})
    with pytest.raises(RuntimeError, match="Certificate verification failed"):
        run_benchmark(create_fixture_engine(tmp_path))


def test_benchmark_fails_if_a_greedy_witness_does_not_replay(tmp_path, monkeypatch):
    original = BindingAuditor.greedy

    def corrupt(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        result["results"][1]["focus"]["score"] += 0.01
        return result

    monkeypatch.setattr(BindingAuditor, "greedy", corrupt)
    with pytest.raises(RuntimeError, match="Greedy witness replay mismatch"):
        run_benchmark(create_fixture_engine(tmp_path))


def test_main_overwrites_stale_success_before_data_loading_can_fail(tmp_path):
    output = tmp_path / "benchmark.json"
    paths = [output, tmp_path / "binding-audit-summary.json"]
    paths.extend(tmp_path / filename for filename in EXAMPLE_FILES.values())
    for path in paths:
        path.write_text('{"status":"passed","old":true}')
    with pytest.raises(FileNotFoundError):
        main(["--data-dir", str(tmp_path / "absent"), "--output", str(output)])
    for path in paths:
        value = json.loads(path.read_text())
        assert value["status"] == "failed"
        assert "old" not in value
        assert value["error_type"] == "FileNotFoundError"


def test_main_publishes_hash_bound_summary_and_verifiable_examples(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    engine = create_fixture_engine(data)
    output = tmp_path / "evidence" / "benchmark.json"
    main(["--data-dir", str(data), "--output", str(output)])
    report = json.loads(output.read_text())
    summary = json.loads((output.parent / "binding-audit-summary.json").read_text())
    assert report["status"] == summary["status"] == "passed"
    assert summary["full_report"]["sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert summary["coverage"] == report["coverage"]
    auditor = BindingAuditor(engine)
    for example in summary["examples"].values():
        assert example["selection_value"] == 0
        assert example["selection_status"] == "no_positive_gap_observed"
        path = output.parent / example["file"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == example["file_sha256"]
        assert auditor.verify(json.loads(path.read_text()))["valid"]
