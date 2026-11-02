"""Complete-cohort accounting and honest publication of mixed-audit experiments."""

from copy import deepcopy
import hashlib
import json

import numpy as np
import pytest

from scripts import benchmark_mixed
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def test_complete_small_workload_has_four_cells_and_two_greedy_orders(tmp_path):
    engine = create_fixture_engine(tmp_path)
    before_scores, before_model = engine.score_matrix().copy(), deepcopy(engine.model)
    report = benchmark_mixed.run_benchmark(engine, top_k=2)
    assert report["status"] == "passed"
    coverage = report["coverage"]
    assert coverage["diseases_total"] == coverage["diseases_processed"] == 2
    assert coverage["candidate_queries"] == coverage["certificates_verified"] == 4
    assert coverage["budget_results"] == 16
    assert coverage["greedy_outcomes_checked"] == 12
    assert coverage["failed_checks"] == 0
    assert [row["robust"] for row in report["summary"]] == [4, 0, 0, 0]
    assert report["interaction_summary"]["both_axes_robust"] == 0
    assert report["interaction_summary"]["new_joint_failures"] == 0
    assert report["examples"]["first_interaction"]["status"] == "unavailable"
    assert report["examples"]["first_query"]["status"] == "passed"
    assert report["examples"]["last_query"]["status"] == "passed"
    assert all(row["exact_failures_missed"] == 0 for row in report["greedy_summary"].values())
    assert all(report["preservation"].values())
    assert np.array_equal(before_scores, engine.score_matrix())
    assert before_model == engine.model
    assert (
        report["input_file_sha256"]["graph.json"]
        == hashlib.sha256((tmp_path / "graph.json").read_bytes()).hexdigest()
    )


def test_no_supported_disease_is_retained_and_cannot_fake_an_example(tmp_path):
    graph = tiny_graph()
    graph["edges"] = [edge for edge in graph["edges"] if edge["type"] != "ASSOCIATES"]
    report = benchmark_mixed.run_benchmark(create_fixture_engine(tmp_path, graph))
    assert report["coverage"]["candidate_queries"] == 0
    assert report["coverage"]["diseases_without_supported_candidates"] == 2
    assert report["coverage"]["diseases_processed"] == 2
    assert report["coverage"]["max_certificate_bytes"] == 0
    assert all(example["status"] == "unavailable" for example in report["examples"].values())
    assert all(row["candidate_queries"] == 0 for row in report["summary"])


def test_interaction_distinguishes_new_failure_from_merely_worse_rank():
    axes = {
        (0, 1): {"robust": True, "worst_supported_rank": 8, "unsupported_attainable": False},
        (1, 0): {"robust": True, "worst_supported_rank": 9, "unsupported_attainable": False},
        (1, 1): {"robust": False, "worst_supported_rank": 11, "unsupported_attainable": False},
    }
    value = benchmark_mixed._interaction(axes)
    assert value["new_joint_failure"] and value["both_axes_robust"]
    assert value["joint_supported_rank_gap"] == 2
    assert not value["new_joint_support_loss"]
    axes[(1, 0)]["robust"] = False
    value = benchmark_mixed._interaction(axes)
    assert not value["new_joint_failure"]
    assert value["joint_supported_rank_gap"] == 2
    axes[(1, 1)]["unsupported_attainable"] = True
    assert benchmark_mixed._interaction(axes)["new_joint_support_loss"]


def test_bad_nested_scope_is_rejected_instead_of_aggregated():
    cells = {
        (0, 1): {"robust": False, "worst_supported_rank": 11, "unsupported_attainable": False},
        (1, 0): {"robust": True, "worst_supported_rank": 8, "unsupported_attainable": False},
        (1, 1): {"robust": True, "worst_supported_rank": 9, "unsupported_attainable": False},
    }
    with pytest.raises(RuntimeError, match="cannot improve"):
        benchmark_mixed._interaction(cells)
    cells[(1, 1)]["worst_supported_rank"] = 12
    with pytest.raises(RuntimeError, match="cannot hold"):
        benchmark_mixed._interaction(cells)


def test_cli_publishes_checksummed_summary_and_fixed_examples(tmp_path):
    create_fixture_engine(tmp_path)
    output = tmp_path / "reports" / "benchmark.json"
    benchmark_mixed.main(["--data-dir", str(tmp_path), "--output", str(output)])
    report = json.loads(output.read_text())
    summary = json.loads((output.parent / "mixed-audit-summary.json").read_text())
    assert report["coverage"]["candidate_queries"] == 6
    assert summary["full_report"] == {
        "file": "benchmark.json",
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    assert "queries" not in summary and summary["summary"] == report["summary"]
    first = json.loads((output.parent / "mixed-audit-example-first.json").read_text())
    assert first["compound"]["id"] == report["queries"][0]["compound_id"]
    assert first["disease"]["id"] == report["queries"][0]["disease_id"]
    last = json.loads((output.parent / "mixed-audit-example-last.json").read_text())
    assert last["compound"]["id"] == report["queries"][-1]["compound_id"]
    assert last["disease"]["id"] == report["queries"][-1]["disease_id"]


def test_failed_rerun_invalidates_every_previous_result(tmp_path, monkeypatch):
    create_fixture_engine(tmp_path)
    output = tmp_path / "benchmark.json"
    paths = [output, *(tmp_path / name for name in benchmark_mixed.REPORT_FILES)]
    for path in paths:
        path.write_text('{"status":"passed"}')

    def fail(*_args, **_kwargs):
        raise RuntimeError("controlled verification failure")

    monkeypatch.setattr(benchmark_mixed, "run_benchmark", fail)
    with pytest.raises(RuntimeError, match="controlled verification"):
        benchmark_mixed.main(["--data-dir", str(tmp_path), "--output", str(output)])
    assert all(json.loads(path.read_text())["status"] == "failed" for path in paths)


def test_execution_rejects_scientific_source_changes(tmp_path, monkeypatch):
    original = benchmark_mixed._source_identity
    calls = []

    def changed_source():
        result = original()
        if calls:
            result["file_sha256"]["app/mixed_audit.py"] = "changed"
        calls.append(True)
        return result

    monkeypatch.setattr(benchmark_mixed, "_source_identity", changed_source)
    with pytest.raises(RuntimeError, match="Scientific source changed"):
        benchmark_mixed.run_benchmark(create_fixture_engine(tmp_path))


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_output_does_not_overwrite_input_through_an_alias(tmp_path, alias):
    create_fixture_engine(tmp_path)
    source = tmp_path / "graph.json"
    before = source.read_bytes()
    output = tmp_path / "output.json"
    if alias == "direct":
        output = source
    elif alias == "symlink":
        output.symlink_to(source)
    else:
        output.hardlink_to(source)
    with pytest.raises(ValueError, match="scientific inputs"):
        benchmark_mixed.main(["--data-dir", str(tmp_path), "--output", str(output)])
    assert source.read_bytes() == before


def test_companion_path_collision_is_rejected(tmp_path):
    create_fixture_engine(tmp_path)
    with pytest.raises(ValueError, match="distinct"):
        benchmark_mixed.main(
            ["--data-dir", str(tmp_path), "--output", str(tmp_path / "mixed-audit-summary.json")]
        )


@pytest.mark.parametrize("top_k", [True, 0, 101, "10"])
def test_invalid_top_k_rejected_before_execution(tmp_path, top_k):
    with pytest.raises(ValueError, match="top_k"):
        benchmark_mixed.run_benchmark(create_fixture_engine(tmp_path), top_k=top_k)
