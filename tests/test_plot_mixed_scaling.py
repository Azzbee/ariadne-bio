"""Figure consistency and statistics on explicitly fabricated unit-test timings."""

from copy import deepcopy
import hashlib
import itertools
import json

import pytest

from scripts import benchmark_mixed_scaling as scaling
from scripts.plot_mixed_scaling import main, render, seed_medians, validate_report


def timing_fixture():
    """This fixture is not a benchmark execution and is never published as research."""
    datasets = []
    for size, groups, seed in itertools.product(scaling.SIZES, scaling.GROUP_COUNTS, scaling.SEEDS):
        rows = []
        for trial in range(1, scaling.TRIALS + 1):
            base = size * groups * seed / 100_000 + trial / 1000
            rows.append(
                {
                    "trial": trial,
                    "timing": {
                        "envelope": {"setup_seconds": 0.01, "solve_seconds": base},
                        "naive": {"setup_seconds": 0.005, "solve_seconds": base * 10},
                    },
                    "checks": {
                        "certificates": 3,
                        "frontier_cells": 12,
                        "literal_matrix_witness_replays": 12,
                    },
                }
            )
        datasets.append(
            {
                "configuration": {"compounds": size, "source_groups": groups, "seed": seed},
                "trials": rows,
            }
        )
    return {
        "status": "passed",
        "source": {"file_sha256": {"test": "fixed"}},
        "source_at_finish": {"file_sha256": {"test": "fixed"}},
        "protocol": {
            "is_full_predeclared_grid": True,
            "compounds": list(scaling.SIZES),
            "source_groups": list(scaling.GROUP_COUNTS),
            "seeds": list(scaling.SEEDS),
            "trials_per_dataset": 3,
            "canonical_baseline_foci": 3,
        },
        "coverage": {
            "datasets": 24,
            "trials": 72,
            "certificates_verified": 216,
            "frontier_cells_compared": 864,
            "literal_matrix_witness_replays": 864,
            "failed_checks": 0,
        },
        "datasets": datasets,
        "summary": scaling.aggregate(datasets),
    }


def test_plot_uses_seed_medians_and_retains_source_hash(tmp_path):
    report = timing_fixture()
    values = seed_medians(report, 4, "envelope")[0]
    assert values["seed_medians_seconds"] == pytest.approx([0.03432, 0.06664, 0.09896])
    assert values["median"] == pytest.approx(0.06664)
    raw = json.dumps(report).encode()
    source_hash = hashlib.sha256(raw).hexdigest()
    receipt = render(report, tmp_path, report_sha256=source_hash)
    assert receipt["source_report_sha256"] == source_hash
    assert receipt["series"]["groups_4/envelope"][0] == values
    for artifact in receipt["artifacts"]:
        path = tmp_path / artifact["file"]
        assert path.stat().st_size == artifact["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact["sha256"]
    svg = (tmp_path / "mixed-scaling-results.svg").read_text()
    assert source_hash in svg
    assert "not a confidence interval" in svg


@pytest.mark.parametrize("corruption", ["grid", "trial", "coverage", "summary", "source"])
def test_incomplete_or_inconsistent_measurements_are_rejected(corruption):
    report = timing_fixture()
    if corruption == "grid":
        report["datasets"][-1] = deepcopy(report["datasets"][0])
    elif corruption == "trial":
        report["datasets"][0]["trials"].pop()
    elif corruption == "coverage":
        report["coverage"]["failed_checks"] = 1
    elif corruption == "summary":
        report["summary"][0]["median_seconds"]["envelope"]["solve_seconds"] = 0.0
    else:
        report["source_at_finish"]["file_sha256"]["test"] = "changed"
    with pytest.raises(ValueError):
        validate_report(report)


@pytest.mark.parametrize("value", [0.0, -1.0, float("inf"), float("nan"), True])
def test_invalid_solve_timings_are_rejected(value):
    report = timing_fixture()
    report["datasets"][0]["trials"][0]["timing"]["envelope"]["solve_seconds"] = value
    with pytest.raises(ValueError, match="Timings"):
        validate_report(report)


def test_failed_render_invalidates_manifest_and_preserves_report(tmp_path):
    source = tmp_path / "report.json"
    report = timing_fixture()
    report["status"] = "running"
    source.write_text(json.dumps(report))
    manifest = tmp_path / "mixed-scaling-figure-manifest.json"
    manifest.write_text('{"status":"passed"}')
    with pytest.raises(ValueError, match="complete predeclared"):
        main([str(source), "--output-dir", str(tmp_path)])
    assert json.loads(manifest.read_text())["status"] == "failed"
    assert json.loads(source.read_text())["status"] == "running"
    with pytest.raises(ValueError, match="overwrite"):
        main([str(manifest), "--output-dir", str(tmp_path)])
