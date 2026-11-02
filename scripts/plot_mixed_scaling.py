"""Plot retained, complete scaling measurements without extrapolating timings."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from pathlib import Path
import statistics

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import ScalarFormatter

from scripts.benchmark_mixed_scaling import GROUP_COUNTS, SEEDS, SIZES, TOP_K, TRIALS, aggregate
from scripts.benchmark_provenance import write_json
from scripts.plot_mixed_benchmark import GREEN, INK, MUTED, ORANGE, PAPER

METHODS = ("envelope", "naive")


def validate_report(report):
    """Check the complete advertised grid, raw timings and derived aggregates."""
    protocol = report["protocol"]
    expected = list(itertools.product(SIZES, GROUP_COUNTS, SEEDS))
    actual = [
        tuple(row["configuration"][key] for key in ("compounds", "source_groups", "seed"))
        for row in report["datasets"]
    ]
    if not (
        report["status"] == "passed"
        and protocol["is_full_predeclared_grid"] is True
        and protocol["compounds"] == list(SIZES)
        and protocol["source_groups"] == list(GROUP_COUNTS)
        and protocol["seeds"] == list(SEEDS)
        and protocol["trials_per_dataset"] == TRIALS
        and protocol["canonical_baseline_foci"] == TOP_K
        and actual == expected
    ):
        raise ValueError("A passed, complete predeclared scaling grid is required")
    trials = []
    for dataset in report["datasets"]:
        rows = dataset["trials"]
        if [row["trial"] for row in rows] != list(range(1, TRIALS + 1)):
            raise ValueError("A dataset has missing or duplicated trials")
        for trial in rows:
            for method in METHODS:
                timing = trial["timing"][method]
                for key in ("setup_seconds", "solve_seconds"):
                    value = timing[key]
                    numeric = not isinstance(value, bool) and isinstance(value, (int, float))
                    if (
                        not numeric
                        or not math.isfinite(value)
                        or value < 0
                        or (key == "solve_seconds" and value == 0)
                    ):
                        raise ValueError(
                            "Timings must be finite, nonnegative and positive for solves"
                        )
            if (
                trial["checks"]["certificates"] != TOP_K
                or trial["checks"]["frontier_cells"] != 4 * TOP_K
            ):
                raise ValueError("A trial did not check the complete frontier")
        trials.extend(rows)
    expected_coverage = {
        "datasets": len(expected),
        "trials": len(trials),
        "certificates_verified": sum(row["checks"]["certificates"] for row in trials),
        "frontier_cells_compared": sum(row["checks"]["frontier_cells"] for row in trials),
        "literal_matrix_witness_replays": sum(
            row["checks"]["literal_matrix_witness_replays"] for row in trials
        ),
        "failed_checks": 0,
    }
    if report["coverage"] != expected_coverage:
        raise ValueError("Scaling coverage disagrees with the retained trials")
    if report["source"]["file_sha256"] != report["source_at_finish"]["file_sha256"]:
        raise ValueError("Scaling scientific source changed during execution")
    if report["summary"] != aggregate(report["datasets"]):
        raise ValueError("Scaling aggregates disagree with the raw paired measurements")
    return report


def seed_medians(report, groups, method):
    """Keep one observed median per graph; repeated trials are not independent graphs."""
    result = []
    for size in SIZES:
        datasets = [
            row
            for row in report["datasets"]
            if row["configuration"]["compounds"] == size
            and row["configuration"]["source_groups"] == groups
        ]
        values = [
            statistics.median(trial["timing"][method]["solve_seconds"] for trial in row["trials"])
            for row in datasets
        ]
        result.append(
            {
                "compounds": size,
                "seed_medians_seconds": values,
                "minimum": min(values),
                "median": statistics.median(values),
                "maximum": max(values),
            }
        )
    return result


def render(report, output_dir, *, report_sha256):
    """Render descriptive observed ranges; no fitted exponent or confidence interval."""
    validate_report(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    with matplotlib.rc_context(
        {"font.family": "DejaVu Sans", "svg.fonttype": "none", "svg.hashsalt": report_sha256}
    ):
        figure = Figure(figsize=(11.8, 6.8), facecolor=PAPER)
        FigureCanvasAgg(figure)
        axes = figure.subplots(1, len(GROUP_COUNTS), sharey=True)
        figure.subplots_adjust(left=0.10, right=0.95, bottom=0.28, top=0.75, wspace=0.18)
        figure.suptitle(
            "Measured scaling of exact joint audits",
            x=0.065,
            y=0.965,
            ha="left",
            fontsize=22,
            fontweight="bold",
            color=INK,
        )
        figure.text(
            0.065,
            0.895,
            "24 synthetic graphs · 3 cold-cache trials per graph · 3 foci per audit",
            fontsize=11,
            color=MUTED,
        )
        series = {}
        for axis, groups in zip(axes, GROUP_COUNTS, strict=True):
            axis.set_facecolor(PAPER)
            axis.set_title(
                f"{groups} source groups",
                loc="left",
                fontsize=12,
                fontweight="bold",
                pad=14,
                color=INK,
            )
            axis.spines[["top", "right"]].set_visible(False)
            for spine in ("left", "bottom"):
                axis.spines[spine].set_color("#d8ddd3")
            axis.set_xscale("log", base=2)
            axis.set_yscale("log")
            axis.set_xticks(SIZES, labels=[str(size) for size in SIZES])
            axis.set_xlim(min(SIZES) * 0.83, max(SIZES) * 1.18)
            axis.tick_params(colors=MUTED, labelsize=9, length=0, pad=7)
            axis.grid(axis="y", color="#e4e7df", linewidth=0.7)
            axis.set_axisbelow(True)
            axis.set_xlabel(
                "Compounds (4 binding records each)", fontsize=10, color=MUTED, labelpad=10
            )
            for method, color, label, marker in (
                ("envelope", GREEN, "Conditional envelopes", "o"),
                ("naive", ORANGE, "Literal full recomputation", "^"),
            ):
                rows = seed_medians(report, groups, method)
                series[f"groups_{groups}/{method}"] = rows
                axis.fill_between(
                    SIZES,
                    [row["minimum"] for row in rows],
                    [row["maximum"] for row in rows],
                    color=color,
                    alpha=0.10,
                )
                axis.plot(
                    SIZES,
                    [row["median"] for row in rows],
                    color=color,
                    marker=marker,
                    markersize=6,
                    linewidth=1.8,
                    label=label,
                )
                for row in rows:
                    axis.scatter(
                        [row["compounds"] * factor for factor in (0.97, 1, 1.03)],
                        row["seed_medians_seconds"],
                        color=color,
                        alpha=0.50,
                        marker=marker,
                        s=15,
                        linewidths=0,
                    )
        axes[0].set_ylabel(
            "Solve time (seconds, logarithmic scale)", fontsize=10, color=MUTED, labelpad=12
        )
        axes[0].yaxis.set_major_formatter(ScalarFormatter())
        handles, labels = axes[0].get_legend_handles_labels()
        figure.legend(
            handles,
            labels,
            loc="lower center",
            bbox_to_anchor=(0.5, 0.14),
            ncol=2,
            frameon=False,
            fontsize=10,
            labelcolor=INK,
        )
        figure.text(
            0.065,
            0.038,
            "Points: each graph's median of 3 trials. Lines: median across 3 seeds. "
            "Shading: their min–max range, not a confidence interval.\n"
            "Solve times exclude setup, shared graph loading and verification; "
            "raw reports retain those costs. Small synthetic family; no extrapolation.\n"
            f"Data: mixed-scaling-benchmark.json · SHA-256 {report_sha256[:24]}…",
            fontsize=8.2,
            color=MUTED,
            linespacing=1.7,
        )
        artifacts = []
        for extension in ("svg", "png"):
            path = output_dir / f"mixed-scaling-results.{extension}"
            metadata = {"Description": f"Scaling benchmark SHA-256: {report_sha256}"}
            if extension == "svg":
                metadata["Date"] = None
            figure.savefig(path, dpi=180, facecolor=PAPER, metadata=metadata)
            artifacts.append(
                {
                    "file": path.name,
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    receipt = {
        "status": "passed",
        "source_report_sha256": report_sha256,
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "matplotlib_version": matplotlib.__version__,
        "statistic": "Per-dataset trial median, then median and descriptive min/max across seeds",
        "series": series,
        "artifacts": artifacts,
    }
    write_json(output_dir / "mixed-scaling-figure-manifest.json", receipt)
    return receipt


def main(argv=None):
    """Invalidate stale success if report validation or rendering fails."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/v1.4.0/scaling"))
    arguments = parser.parse_args(argv)
    paths = [
        arguments.output_dir / name
        for name in (
            "mixed-scaling-results.svg",
            "mixed-scaling-results.png",
            "mixed-scaling-figure-manifest.json",
        )
    ]
    for path in paths:
        if path.resolve() == arguments.report.resolve() or (
            path.exists() and path.samefile(arguments.report)
        ):
            raise ValueError("Figure output must not overwrite the source report")
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = paths[-1]
    write_json(manifest, {"status": "running", "source_report": str(arguments.report)})
    try:
        raw = arguments.report.read_bytes()
        receipt = render(
            json.loads(raw), arguments.output_dir, report_sha256=hashlib.sha256(raw).hexdigest()
        )
    except BaseException as error:
        write_json(
            manifest, {"status": "failed", "error_type": type(error).__name__, "error": str(error)}
        )
        raise
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
