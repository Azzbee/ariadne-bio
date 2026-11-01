"""Research figures must derive from complete, internally consistent reports."""

import hashlib
import json

import pytest

from scripts.benchmark_mixed import run_benchmark
from scripts.plot_mixed_benchmark import main, render, validate_report
from tests.test_graph_engine import create_fixture_engine


def test_figure_retains_source_identity_and_actual_zero_interaction(tmp_path):
    report = run_benchmark(create_fixture_engine(tmp_path), top_k=2)
    raw = json.dumps(report).encode()
    report_sha = hashlib.sha256(raw).hexdigest()
    receipt = render(report, tmp_path / "figures", report_sha256=report_sha)
    assert receipt["status"] == "passed"
    assert receipt["candidate_queries"] == 4
    assert receipt["source_report_sha256"] == report_sha
    assert len(receipt["artifacts"]) == 2
    for artifact in receipt["artifacts"]:
        path = tmp_path / "figures" / artifact["file"]
        assert artifact["bytes"] == path.stat().st_size
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    svg = (tmp_path / "figures" / "mixed-audit-results.svg").read_text()
    assert report_sha in svg
    assert "4 baseline top-2 hypotheses" in svg
    assert "Fail only joint" in svg


def test_figure_rejects_a_tampered_aggregate(tmp_path):
    report = run_benchmark(create_fixture_engine(tmp_path), top_k=2)
    report["interaction_summary"]["new_joint_failures"] = 3
    with pytest.raises(ValueError, match="Saved summary"):
        validate_report(report)


def test_figure_rejects_partial_and_duplicate_cohorts(tmp_path):
    report = run_benchmark(create_fixture_engine(tmp_path), top_k=2)
    report["coverage"]["diseases_processed"] = 1
    with pytest.raises(ValueError, match="coverage"):
        validate_report(report)
    report["coverage"]["diseases_processed"] = 2
    report["queries"][1] = report["queries"][0]
    with pytest.raises(ValueError, match="coverage"):
        validate_report(report)
    report["status"] = "running"
    with pytest.raises(ValueError, match="passed, complete"):
        validate_report(report)


def test_output_cannot_replace_source_report(tmp_path):
    source = tmp_path / "mixed-audit-results.svg"
    source.write_text('{"status":"passed"}')
    with pytest.raises(ValueError, match="overwrite"):
        main([str(source), "--output-dir", str(tmp_path)])
    assert source.read_text() == '{"status":"passed"}'


def test_failed_rerender_invalidates_previous_figure_manifest(tmp_path):
    source = tmp_path / "report.json"
    source.write_text('{"status":"failed"}')
    output = tmp_path / "figures"
    output.mkdir()
    manifest = output / "mixed-audit-figure-manifest.json"
    manifest.write_text('{"status":"passed","source_report_sha256":"old"}')
    with pytest.raises(ValueError, match="passed, complete"):
        main([str(source), "--output-dir", str(output)])
    assert json.loads(manifest.read_text())["status"] == "failed"
