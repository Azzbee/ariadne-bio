"""Whole-cohort accounting, preservation and failure publication for group audits."""

import json
from pathlib import Path

import numpy as np
import pytest

from scripts import benchmark_provenance
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def test_small_benchmark_accounts_for_every_query_and_comparison(tmp_path):
    engine = create_fixture_engine(tmp_path)
    scores, model = engine.score_matrix().copy(), json.dumps(engine.model, sort_keys=True)
    report = benchmark_provenance.run_benchmark(engine, top_k=2)
    assert report["status"] == "passed"
    assert report["coverage"]["diseases_processed"] == 2
    assert report["coverage"]["candidate_queries"] == 4
    assert report["coverage"]["certificates_verified"] == 4
    assert report["coverage"]["protection_feasibility_checks"] == 8
    assert report["coverage"]["distinct_source_scenarios_per_disease"] == 2
    assert report["coverage"]["budget_results"] == 12
    assert report["summary"][0]["robust"] == 4
    assert report["summary"][2]["fragile"] == 4
    assert report["protection_summary"]["minimum_group_count_histogram"] == {"1": 4}
    assert report["protection_summary"]["greedy_suboptimal_queries"] == 0
    assert report["examples"]["source"]["status"] == "unavailable"
    assert report["examples"]["pubmed"]["status"] == "unavailable"
    assert np.array_equal(scores, engine.score_matrix())
    assert json.dumps(engine.model, sort_keys=True) == model


def test_zero_supported_diseases_are_retained_not_silently_dropped(tmp_path):
    graph = tiny_graph()
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "ASSOCIATES"]
    report = benchmark_provenance.run_benchmark(create_fixture_engine(tmp_path, graph))
    assert report["coverage"]["diseases_processed"] == 2
    assert report["coverage"]["diseases_without_supported_candidates"] == 2
    assert report["coverage"]["candidate_queries"] == 0
    assert report["coverage"]["max_certificate_bytes"] == 0
    assert report["queries"] == []
    assert all(row["candidate_queries"] == 0 for row in report["summary"])


def test_cli_publishes_whole_report_and_checksummed_summary(tmp_path):
    create_fixture_engine(tmp_path)
    output = tmp_path / "reports" / "benchmark.json"
    benchmark_provenance.main(["--data-dir", str(tmp_path), "--output", str(output)])
    report = json.loads(output.read_text())
    summary = json.loads((output.parent / "provenance-audit-summary.json").read_text())
    assert report["coverage"]["candidate_queries"] == 6
    assert summary["full_report"]["file"] == output.name
    assert "queries" not in summary
    assert summary["summary"] == report["summary"]
    assert (output.parent / "provenance-catalog.json").exists()


def test_failed_rerun_invalidates_every_old_success(tmp_path, monkeypatch):
    create_fixture_engine(tmp_path)
    output = tmp_path / "benchmark.json"
    for path in [output, *(tmp_path / name for name in benchmark_provenance.REPORT_FILES)]:
        path.write_text('{"status":"passed"}')

    def fail(*_args, **_kwargs):
        raise RuntimeError("deliberate oracle failure")

    monkeypatch.setattr(benchmark_provenance, "run_benchmark", fail)
    with pytest.raises(RuntimeError, match="oracle failure"):
        benchmark_provenance.main(["--data-dir", str(tmp_path), "--output", str(output)])
    for path in [output, *(tmp_path / name for name in benchmark_provenance.REPORT_FILES)]:
        assert json.loads(path.read_text())["status"] == "failed"


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_output_cannot_destroy_input_even_through_alias(tmp_path, alias):
    create_fixture_engine(tmp_path)
    graph = tmp_path / "graph.json"
    before = graph.read_bytes()
    output = tmp_path / "output.json"
    if alias == "direct":
        output = graph
    elif alias == "symlink":
        output.symlink_to(graph)
    else:
        output.hardlink_to(graph)
    with pytest.raises(ValueError, match="inputs"):
        benchmark_provenance.main(["--data-dir", str(tmp_path), "--output", str(output)])
    assert graph.read_bytes() == before


def test_colliding_companion_path_is_rejected(tmp_path):
    create_fixture_engine(tmp_path)
    with pytest.raises(ValueError, match="distinct"):
        benchmark_provenance.main(
            ["--data-dir", str(tmp_path), "--output", str(tmp_path / "provenance-catalog.json")]
        )


def test_predictable_tmp_symlink_cannot_overwrite_input(tmp_path):
    create_fixture_engine(tmp_path)
    graph = tmp_path / "graph.json"
    before = graph.read_bytes()
    output = tmp_path / "benchmark.json"
    Path(f"{output}.tmp").symlink_to(graph)
    benchmark_provenance.main(["--data-dir", str(tmp_path), "--output", str(output)])
    assert graph.read_bytes() == before


@pytest.mark.parametrize("top_k", [True, 0, 101, "10"])
def test_bad_top_k_is_rejected(tmp_path, top_k):
    with pytest.raises(ValueError, match="top_k"):
        benchmark_provenance.run_benchmark(create_fixture_engine(tmp_path), top_k=top_k)
