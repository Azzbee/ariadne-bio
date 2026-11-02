"""Render publication figures from a complete, validated mixed-audit report."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from scripts.benchmark_mixed import CELLS, _aggregate
from scripts.benchmark_provenance import write_json

GREEN = "#214b40"
LIME = "#b9cd58"
INK = "#182821"
ORANGE = "#b96340"
PAPER = "#faf9f4"
MUTED = "#59645e"


def validate_report(report):
    """Reject partial or inconsistent evidence before drawing a scientific claim."""
    if report.get("status") != "passed":
        raise ValueError("A passed, complete benchmark is required")
    rows = report["queries"]
    coverage = report["coverage"]
    keys = {(row["disease_id"], row["compound_id"]) for row in rows}
    consistent = [
        len(keys) == len(rows),
        coverage["candidate_queries"] == len(rows),
        coverage["certificates_verified"] == len(rows),
        coverage["budget_results"] == len(CELLS) * len(rows),
        coverage["diseases_total"] == coverage["diseases_processed"],
        coverage["failed_checks"] == 0,
        all(report["preservation"].values()),
    ]
    if not all(consistent):
        raise ValueError("Report coverage or preservation is inconsistent")
    for row in rows:
        if [(cell["group_budget"], cell["edge_budget"]) for cell in row["results"]] != list(CELLS):
            raise ValueError("Incomplete or misordered budget frontier")
    aggregate = _aggregate(rows)
    if aggregate != (report["summary"], report["interaction_summary"], report["greedy_summary"]):
        raise ValueError("Saved summary differs from query-level observations")
    return report


def _style(axis, title):
    axis.set_title(title, loc="left", fontweight="bold", fontsize=12, pad=15, color=INK)
    axis.set_facecolor(PAPER)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.spines["bottom"].set_color("#d8ddd3")
    axis.tick_params(axis="both", colors=MUTED, labelsize=9, length=0, pad=7)
    axis.set_axisbelow(True)
    axis.grid(axis="x", color="#e4e7df", linewidth=0.7)
    axis.xaxis.set_major_locator(MaxNLocator(integer=True))


def _bar_labels(axis, bars, values):
    for rectangle, value in zip(bars, values):
        axis.annotate(
            f"{value:,}",
            (rectangle.get_width(), rectangle.get_y() + rectangle.get_height() / 2),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=10,
            fontweight="bold",
            color=INK,
        )


def _save_figure(figure, output_dir, report_sha256):
    artifacts = []
    for extension in ("svg", "png"):
        path = output_dir / f"mixed-audit-results.{extension}"
        metadata = {"Description": f"Benchmark SHA-256: {report_sha256}"}
        if extension == "svg":
            metadata["Date"] = None
        figure.savefig(path, dpi=180, metadata=metadata)
        artifacts.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    figure.clear()
    return artifacts


def render(report, output_dir, *, report_sha256):
    """Create SVG/PNG figures and retain their data-source checksum and counts."""
    validate_report(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    matplotlib.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "svg.fonttype": "none",
            "svg.hashsalt": report_sha256,
            "figure.facecolor": PAPER,
            "savefig.facecolor": PAPER,
            "axes.labelcolor": MUTED,
        }
    )
    figure = Figure(figsize=(12, 8.2))
    FigureCanvasAgg(figure)
    axes = figure.subplots(2, 2)
    figure.subplots_adjust(left=0.19, right=0.94, top=0.83, bottom=0.23, wspace=0.78, hspace=0.85)
    figure.suptitle(
        "When evidence changes together",
        x=0.065,
        y=0.965,
        ha="left",
        fontsize=23,
        fontweight="bold",
        color=INK,
    )
    count = report["coverage"]["candidate_queries"]
    figure.text(
        0.065,
        0.902,
        f"{count:,} baseline top-{report['protocol']['top_k']} hypotheses · "
        f"{report['coverage']['diseases_processed']} diseases · "
        "one fixed model · every rival included",
        color=MUTED,
        fontsize=11,
    )

    axis = axes[0, 0]
    _style(axis, "A   Certified robust in each scope")
    values = [cell["robust"] for cell in report["summary"][1:]]
    bars = axis.barh(
        ["One record", "One group", "Group + record"],
        values,
        color=["#86a99b", GREEN, ORANGE],
        height=0.56,
    )
    _bar_labels(axis, bars, values)
    axis.invert_yaxis()
    axis.set_xlim(0, max([1, *values]) * 1.24)
    axis.set_xlabel("Hypotheses remaining in supported top k", fontsize=9, labelpad=10)

    axis = axes[0, 1]
    _style(axis, "B   What separate audits miss")
    interaction = report["interaction_summary"]
    both = interaction["both_axes_robust"]
    new_failure = interaction["new_joint_failures"]
    values = [both, both - new_failure, new_failure]
    bars = axis.barh(
        ["Pass both axes", "Also pass joint", "Fail only joint"],
        values,
        color=[GREEN, LIME, ORANGE],
        height=0.56,
    )
    _bar_labels(axis, bars, values)
    axis.invert_yaxis()
    axis.set_xlim(0, max([1, *values]) * 1.24)
    axis.set_xlabel("Hypotheses passing each condition", fontsize=9, labelpad=10)

    axis = axes[1, 0]
    _style(axis, "C   Same-scope failure discovery")
    exact = report["summary"][-1]["fragile"]
    baseline = report["greedy_summary"]
    values = [exact, baseline["strongest"]["failures_found"]]
    bars = axis.barh(
        ["Exact joint audit", "Best of both\ngreedy orders"],
        values,
        color=[GREEN, LIME],
        height=0.5,
    )
    _bar_labels(axis, bars, values)
    axis.invert_yaxis()
    axis.set_xlim(0, max([1, *values]) * 1.2)
    axis.set_xlabel("Failures found within the identical joint scope", fontsize=9, labelpad=10)

    axis = axes[1, 1]
    _style(axis, "D   Precision beyond a failure flag")
    gaps = [
        row["greedy"]["strongest"]["supported_rank_gap"]
        for row in report["queries"]
        if row["greedy"]["strongest"]["supported_rank_gap"] is not None
    ]
    values = [
        sum(value == 0 for value in gaps),
        sum(value > 0 for value in gaps),
        count - len(gaps),
    ]
    bars = axis.barh(
        ["Same worst rank", "Greedy rank\nunderestimates", "Greedy finds\nno-support state"],
        values,
        color=[LIME, ORANGE, "#b6bdb3"],
        height=0.56,
    )
    _bar_labels(axis, bars, values)
    axis.invert_yaxis()
    axis.set_xlim(0, max([1, *values]) * 1.25)
    axis.set_xlabel("Hypotheses by comparator outcome", fontsize=9, labelpad=10)

    figure.text(
        0.065,
        0.045,
        "Scope: at most one selected source-label withdrawal plus one surviving BINDS record.\n"
        "A group may remove many records. Counts describe finite model sensitivity, "
        "not efficacy or error probabilities.\n"
        f"Data: mixed-audit-benchmark.json · SHA-256 {report_sha256[:24]}…",
        fontsize=8.5,
        color=MUTED,
        linespacing=1.6,
    )
    artifacts = _save_figure(figure, output_dir, report_sha256)
    receipt = {
        "status": "passed",
        "source_report_sha256": report_sha256,
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "matplotlib_version": matplotlib.__version__,
        "candidate_queries": count,
        "artifacts": artifacts,
    }
    write_json(output_dir / "mixed-audit-figure-manifest.json", receipt)
    return receipt


def main(argv=None):
    """Render verified query counts, preserving a checksum link to the full report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/v1.4.0"))
    arguments = parser.parse_args(argv)
    outputs = (
        arguments.output_dir / f"mixed-audit-results.{extension}" for extension in ("svg", "png")
    )
    for path in (*outputs, arguments.output_dir / "mixed-audit-figure-manifest.json"):
        if path.resolve() == arguments.report.resolve() or (
            path.exists() and path.samefile(arguments.report)
        ):
            raise ValueError("Figure output must not overwrite the source report")
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = arguments.output_dir / "mixed-audit-figure-manifest.json"
    write_json(manifest, {"status": "running", "source_report": str(arguments.report)})
    try:
        raw = arguments.report.read_bytes()
        receipt = render(
            json.loads(raw), arguments.output_dir, report_sha256=hashlib.sha256(raw).hexdigest()
        )
    except BaseException as error:
        write_json(
            manifest,
            {
                "status": "failed",
                "source_report": str(arguments.report),
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
