"""Measure exact joint group/record audits on the complete supported top-k cohort.

Every certificate is recomputed and independently matrix-replayed. Two strong
greedy operation orders use the same threat space. Results, including null
interaction and comparator findings, are retained without favorable-case filters.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import scipy

from app.graph_engine import GraphEngine
from app.mixed_audit import MixedAuditor
from scripts.benchmark_provenance import write_json

CELLS = ((0, 0), (0, 1), (1, 0), (1, 1))
ORDERS = ("source_first", "edge_first", "strongest")
EXAMPLES = {
    "first_query": "mixed-audit-example-first.json",
    "last_query": "mixed-audit-example-last.json",
    "first_interaction": "mixed-audit-example-interaction.json",
    "largest_rank_gap": "mixed-audit-example-rank-gap.json",
    "largest_greedy_gap": "mixed-audit-example-greedy-gap.json",
}
REPORT_FILES = ("mixed-audit-summary.json", *EXAMPLES.values())
SOURCE_FILES = (
    "app/audit_numerics.py",
    "app/binding_audit.py",
    "app/provenance_audit.py",
    "app/mixed_audit.py",
    "app/graph_engine.py",
    "scripts/benchmark_mixed.py",
    "scripts/benchmark_provenance.py",
)
INPUT_FILES = ("graph.json", "model.json", "manifest.json", "evaluation.json")


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _source_identity():
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        revision, dirty = None, None
    return {
        "git_revision": revision,
        "working_tree_dirty": dirty,
        "file_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in SOURCE_FILES
        },
    }


def _input_identity(engine):
    return {
        name: (
            hashlib.sha256((engine.data_dir / name).read_bytes()).hexdigest()
            if (engine.data_dir / name).is_file()
            else None
        )
        for name in INPUT_FILES
    }


def _result_map(certificate):
    rows = certificate["results"]
    mapped = {(row["group_budget"], row["edge_budget"]): row for row in rows}
    _require(len(rows) == 4 and set(mapped) == set(CELLS), "Incomplete mixed frontier")
    return mapped


def _witness_ids(witness):
    if witness is None:
        return None
    return {
        key: witness[key]
        for key in (
            "group_ids",
            "residual_edge_ids",
            "removed_edge_count",
            "removed_edge_ids_sha256",
        )
    }


def _frontier(certificate):
    mapped = _result_map(certificate)
    result = []
    for cell in CELLS:
        row = mapped[cell]
        result.append(
            {
                key: row[key]
                for key in (
                    "group_budget",
                    "edge_budget",
                    "worst_supported_rank",
                    "unsupported_attainable",
                    "robust",
                    "covered_action_representations",
                )
            }
        )
        result[-1].update(
            {name: _witness_ids(row[name]) for name in ("rank_witness", "unsupported_witness")}
        )
    return result


def _interaction(cells):
    """Keep top-k failure, worst-supported-rank change and support loss distinct."""
    edges, groups, joint = cells[(0, 1)], cells[(1, 0)], cells[(1, 1)]
    both_axes_robust = edges["robust"] and groups["robust"]
    ranks = [row["worst_supported_rank"] for row in (edges, groups, joint)]
    gap = ranks[2] - max(ranks[:2]) if all(rank is not None for rank in ranks) else None
    _require(gap is None or gap >= 0, "Joint scope cannot improve a worst-supported-rank bound")
    _require(
        not joint["robust"] or both_axes_robust,
        "Joint robustness cannot hold when an included axis fails",
    )
    return {
        "both_axes_robust": both_axes_robust,
        "new_joint_failure": both_axes_robust and not joint["robust"],
        "joint_supported_rank_gap": gap,
        "new_joint_support_loss": joint["unsupported_attainable"]
        and not edges["unsupported_attainable"]
        and not groups["unsupported_attainable"],
    }


def _check_greedy(auditor, certificate):
    disease, compound = certificate["disease"]["id"], certificate["compound"]["id"]
    greedy = auditor.greedy(disease, compound, top_k=certificate["top_k"])
    joint = _result_map(certificate)[(1, 1)]
    replayed = set()
    for name in ORDERS:
        outcome = greedy[name]
        key = tuple(outcome["group_ids"]), tuple(outcome["residual_edge_ids"])
        if key not in replayed:
            actual = auditor.replay(disease, compound, *key)
            _require(actual["focus"] == outcome["focus"], "Greedy matrix witness mismatch")
            replayed.add(key)
        final = outcome["focus"]
        failure = not final["supported"] or final["rank"] > certificate["top_k"]
        _require(failure == outcome["failure_found"], "Greedy failure flag is inconsistent")
        _require(not failure or not joint["robust"], "Greedy exceeds allegedly exact robustness")
        if final["supported"]:
            gap = joint["worst_supported_rank"] - final["rank"]
            _require(gap >= 0, "Greedy rank exceeds allegedly exact bound")
        else:
            _require(joint["unsupported_attainable"], "Greedy support loss exceeds exact bound")
            gap = None
        outcome["supported_rank_gap"] = gap
    _require(
        greedy["strongest"]["failure_found"]
        == any(greedy[name]["failure_found"] for name in ORDERS[:2]),
        "Combined greedy failure discovery does not match its two orders",
    )
    return greedy, len(replayed)


def _query(auditor, disease, candidate, top_k):
    started = time.perf_counter()
    certificate = auditor.audit(disease, candidate["id"], top_k=top_k)
    verification = auditor.verify(certificate)
    _require(verification["valid"], f"Mixed certificate invalid: {verification['errors']}")
    _require(
        candidate["rank"] == certificate["baseline"]["rank"]
        and candidate["score"] == certificate["baseline"]["score"],
        "Cohort baseline does not match the audited baseline",
    )
    greedy, replayed = _check_greedy(auditor, certificate)
    row = {
        "disease_id": disease,
        "compound_id": candidate["id"],
        "compound_name": candidate["name"],
        "baseline_rank": certificate["baseline"]["rank"],
        "baseline_score": certificate["baseline"]["score"],
        "certificate_sha256": certificate["certificate_sha256"],
        "certificate_bytes": len(json.dumps(certificate, separators=(",", ":")).encode()),
        "certificate_witnesses_replayed": verification["replayed_witnesses"],
        "greedy_witnesses_replayed": replayed,
        "results": _frontier(certificate),
        "interaction": _interaction(_result_map(certificate)),
        "greedy": greedy,
        "proof": certificate["proof"],
        "runtime_seconds": time.perf_counter() - started,
    }
    return row, certificate, verification


def _examples(previous, row, certificate, verification):
    """Selection is explicit and post hoc; never label examples as a held-out set."""
    criteria = {
        "first_query": (True, 1, "First supported query in canonical disease/rank order"),
        "last_query": (
            True,
            previous.get("last_query", {}).get("selection_value", 0) + 1,
            "Last supported query in canonical disease/rank order",
        ),
        "first_interaction": (
            row["interaction"]["new_joint_failure"],
            1,
            "First interaction failure in canonical disease/compound order",
        ),
        "largest_rank_gap": (
            (row["interaction"]["joint_supported_rank_gap"] or 0) > 0,
            row["interaction"]["joint_supported_rank_gap"],
            "Largest joint worst-supported-rank gap over the maximum of both axes",
        ),
        "largest_greedy_gap": (
            (row["greedy"]["strongest"]["supported_rank_gap"] or 0) > 0,
            row["greedy"]["strongest"]["supported_rank_gap"],
            "Largest exact supported-rank gap over the stronger of both greedy orders",
        ),
    }
    for name, (eligible, value, rule) in criteria.items():
        if eligible and (name not in previous or value > previous[name]["selection_value"]):
            previous[name] = {
                "status": "passed",
                "selection": f"Post hoc illustration: {rule}; not independent validation",
                "selection_value": value,
                "certificate": certificate,
                "verification": verification,
                "greedy": row["greedy"],
                "interaction": row["interaction"],
            }


def _aggregate(rows):
    cells = []
    for index, (groups, edges) in enumerate(CELLS):
        results = [row["results"][index] for row in rows]
        cells.append(
            {
                "group_budget": groups,
                "edge_budget": edges,
                "candidate_queries": len(rows),
                "robust": sum(row["robust"] for row in results),
                "fragile": sum(not row["robust"] for row in results),
                "unsupported_attainable": sum(row["unsupported_attainable"] for row in results),
            }
        )
    interactions = [row["interaction"] for row in rows]
    interaction = {
        "candidate_queries": len(rows),
        "both_axes_robust": sum(row["both_axes_robust"] for row in interactions),
        "new_joint_failures": sum(row["new_joint_failure"] for row in interactions),
        "new_joint_support_loss": sum(row["new_joint_support_loss"] for row in interactions),
        "joint_rank_worse_than_both_axes": sum(
            (row["joint_supported_rank_gap"] or 0) > 0 for row in interactions
        ),
        "maximum_joint_supported_rank_gap": max(
            (row["joint_supported_rank_gap"] or 0 for row in interactions), default=0
        ),
    }
    greedy = {}
    for name in ORDERS:
        results = [row["greedy"][name] for row in rows]
        greedy[name] = {
            "candidate_queries": len(rows),
            "failures_found": sum(row["failure_found"] for row in results),
            "exact_failures_missed": sum(
                not row["results"][-1]["robust"] and not row["greedy"][name]["failure_found"]
                for row in rows
            ),
            "unsupported_found": sum(not row["focus"]["supported"] for row in results),
            "worst_supported_rank_underestimates": sum(
                (row["supported_rank_gap"] or 0) > 0 for row in results
            ),
            "maximum_supported_rank_gap": max(
                (row["supported_rank_gap"] or 0 for row in results), default=0
            ),
        }
    return cells, interaction, greedy


def run_benchmark(engine, *, top_k=10, progress=False):
    """Audit every declared disease and supported baseline candidate without fitting."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
        raise ValueError("top_k must be an integer from 1 through 100")
    started = time.perf_counter()
    source, inputs = _source_identity(), _input_identity(engine)
    before_model = json.dumps(engine.model, sort_keys=True)
    before_scores = engine.score_matrix().copy()
    auditor = MixedAuditor(engine)
    rows, diseases, examples, identity = [], [], {}, None
    for disease in engine.entities["Disease"]:
        disease_started = time.perf_counter()
        candidates = auditor.baseline_candidates(disease, limit=top_k)
        for candidate in candidates:
            row, certificate, verification = _query(auditor, disease, candidate, top_k)
            rows.append(row)
            identity = certificate["identity"]
            _examples(examples, row, certificate, verification)
        diseases.append(
            {
                "disease_id": disease,
                "name": engine.nodes[disease]["name"],
                "candidate_queries": len(candidates),
                "runtime_seconds": time.perf_counter() - disease_started,
            }
        )
        if progress:
            interactions = sum(row["interaction"]["new_joint_failure"] for row in rows)
            print(
                f"{len(diseases)}/{len(engine.entities['Disease'])} diseases; "
                f"{len(rows)} certificates verified; {interactions} interaction failures",
                flush=True,
            )
    after_source, after_inputs = _source_identity(), _input_identity(engine)
    _require(source["file_sha256"] == after_source["file_sha256"], "Scientific source changed")
    _require(inputs == after_inputs, "Scientific input bytes changed")
    _require(json.dumps(engine.model, sort_keys=True) == before_model, "Fitted model changed")
    _require(np.array_equal(engine.score_matrix(), before_scores), "Legacy explorer scores changed")
    _require(
        len(rows) == sum(row["candidate_queries"] for row in diseases), "Incomplete cohort coverage"
    )
    summary, interaction, greedy = _aggregate(rows)
    for name in EXAMPLES:
        examples.setdefault(
            name,
            {
                "status": "unavailable",
                "reason": "No query met the declared post hoc selection criterion",
            },
        )
    return {
        "schema_version": "1.0",
        "title": "Exact simultaneous provenance-group and residual-record audit benchmark",
        "status": "passed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "source_at_finish": after_source,
        "input_file_sha256": inputs,
        "identity": identity,
        "protocol": {
            "population": "Every graph disease and its canonical baseline supported top-k",
            "top_k": top_k,
            "budget_cells": [list(cell) for cell in CELLS],
            "group_scope": "Every observed BINDS provider label, at most one withdrawal",
            "record_scope": "At most one additional surviving BINDS record anywhere in the graph",
            "competitors": "All graph compounds, jointly reranked without model refitting",
            "comparison": (
                "Both greedy operation orders use the identical joint threat space; first "
                "action uses rank with rank-boundary margin ties, second action optimized. "
                "The strongest combined outcome is reported even when it equals exact search."
            ),
            "interaction": "Both one-operation axes robust but a permitted joint scenario fails",
            "verification": (
                "Every certificate separately recomputed and distinct witnesses independently "
                "replayed by full sparse matrix edits; every greedy witness also replayed"
            ),
            "maximality_oracle": "Independent exhaustive joint-world tests in test_mixed_audit.py",
            "work_count_semantics": (
                "Conditional local compound states and covered action representations count "
                "different work units; action representations may duplicate edited graphs; "
                "neither their ratio nor repeated cache use is a measured speedup"
            ),
            "runtime_scope": (
                "One process wall time including initialization, cohort construction, exact "
                "verification and both greedy orders; not isolated single-query latency"
            ),
            "interpretation": (
                "Finite fixed-model sensitivity, not source independence, biological synergy, "
                "error probability, efficacy, or prospective commercial value"
            ),
        },
        "coverage": {
            "diseases_total": len(engine.entities["Disease"]),
            "diseases_processed": len(diseases),
            "diseases_without_supported_candidates": sum(
                row["candidate_queries"] == 0 for row in diseases
            ),
            "candidate_queries": len(rows),
            "budget_results": len(CELLS) * len(rows),
            "certificates_verified": len(rows),
            "certificate_witness_replays": sum(
                row["certificate_witnesses_replayed"] for row in rows
            ),
            "greedy_witness_replays": sum(row["greedy_witnesses_replayed"] for row in rows),
            "greedy_outcomes_checked": len(ORDERS) * len(rows),
            "candidate_universe": len(engine.entities["Compound"]),
            "failed_checks": 0,
            "max_certificate_bytes": max((row["certificate_bytes"] for row in rows), default=0),
        },
        "summary": summary,
        "interaction_summary": interaction,
        "greedy_summary": greedy,
        "preservation": {
            "scientific_module_bytes_unchanged": True,
            "input_file_bytes_unchanged": True,
            "fitted_model_unchanged": True,
            "legacy_scores_unchanged": True,
        },
        "diseases": diseases,
        "queries": rows,
        "examples": examples,
        "runtime_seconds": time.perf_counter() - started,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
        },
    }


def _outputs(output):
    return [output, *(output.parent / name for name in REPORT_FILES)]


def _guard_outputs(output, data_dir):
    outputs = _outputs(output)
    if len(outputs) != len({path.resolve() for path in outputs}):
        raise ValueError("Output paths must be distinct")
    for destination in outputs:
        for name in INPUT_FILES:
            source = data_dir / name
            if destination.resolve() == source.resolve() or (
                destination.exists() and source.exists() and destination.samefile(source)
            ):
                raise ValueError("Benchmark output must not overwrite scientific inputs")


def _status(output, value):
    for path in _outputs(output):
        write_json(path, value)


def _publish(output, report):
    write_json(output, report)
    for name, filename in EXAMPLES.items():
        example = report["examples"][name]
        write_json(output.parent / filename, example.get("certificate", example))
    summary = {
        key: value
        for key, value in report.items()
        if key not in ("queries", "diseases", "examples")
    }
    summary["full_report"] = {
        "file": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    summary["examples"] = {
        name: {"file": filename, "status": report["examples"][name]["status"]}
        for name, filename in EXAMPLES.items()
    }
    write_json(output.parent / "mixed-audit-summary.json", summary)


def main(argv=None):
    """Publish a complete result, or invalidate stale success after a failed run."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/v1.4.0/mixed-audit-benchmark.json")
    )
    arguments = parser.parse_args(argv)
    _guard_outputs(arguments.output, arguments.data_dir)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    _status(arguments.output, {"status": "running", "started_at": started_at})
    try:
        report = run_benchmark(GraphEngine(arguments.data_dir), progress=True)
        report["invocation"] = {
            "module": "scripts.benchmark_mixed",
            "data_dir": str(arguments.data_dir),
            "output": str(arguments.output),
        }
        _publish(arguments.output, report)
    except BaseException as error:
        _status(
            arguments.output,
            {
                "status": "failed",
                "started_at": started_at,
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "coverage",
                    "summary",
                    "interaction_summary",
                    "greedy_summary",
                    "runtime_seconds",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
