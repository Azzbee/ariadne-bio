"""Benchmark every disease's supported top ten with exact, replayed rank audits.

No fitting, favorable-case selection or clinical efficacy inference occurs here.
Every certificate and greedy witness is independently replayed through edited
sparse matrices. The exhaustive maximality oracle lives in the scientific tests.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import scipy

from app.binding_audit import BindingAuditor, canonical_scores
from app.graph_engine import GraphEngine
from scripts.prepare_data import write_json

EXAMPLE_FILES = {
    "largest_competitor_rank_gap": "binding-audit-example-competitor.json",
    "largest_greedy_supported_rank_gap": "binding-audit-example-greedy.json",
    "largest_strong_greedy_supported_rank_gap": "binding-audit-example-strong-greedy.json",
    "scope_verdict_difference": "binding-audit-example-scope.json",
}


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _source_identity():
    root = Path(__file__).resolve().parents[1]
    files = ["app/binding_audit.py", "app/graph_engine.py", "scripts/benchmark_audits.py"]
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
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
    return {"git_revision": revision, "working_tree_dirty": dirty, "file_sha256": hashes}


def _numerical_comparison(engine):
    counts = engine.path_counts
    scores, _ = canonical_scores(
        counts,
        engine.endpoint_degrees["Compound"][:, None],
        engine.endpoint_degrees["Disease"][None, :],
        engine.model,
    )
    legacy = engine.score_matrix()
    rank_differences = 0
    for disease in range(scores.shape[1]):
        supported = np.flatnonzero(counts[:, disease].sum(axis=1) > 0)
        audit_order = supported[np.lexsort((supported, -scores[supported, disease]))]
        legacy_order = supported[np.lexsort((supported, -legacy[supported, disease]))]
        rank_differences += int(np.count_nonzero(audit_order != legacy_order))
    return {
        "pairs_compared": int(scores.size),
        "max_absolute_score_difference": (
            float(np.max(np.abs(scores - legacy))) if scores.size else 0
        ),
        "nonidentical_score_pairs": int(np.count_nonzero(scores != legacy)),
        "supported_rank_position_differences": rank_differences,
        "legacy_model_and_scorer_changed": False,
        "interpretation": (
            "Audit scores use explicit fixed-order binary64 arithmetic. Legacy scores use BLAS; "
            "small last-bit differences are disclosed, not hidden with display rounding."
        ),
    }


def _check_greedy(auditor, certificate, *, score_tiebreak):
    disease_id, compound_id = certificate["disease"]["id"], certificate["compound"]["id"]
    top_k = certificate["top_k"]
    greedy = auditor.greedy(
        disease_id, compound_id, budget=2, score_tiebreak=score_tiebreak, top_k=top_k
    )
    replayed, results = set(), []
    for exact, heuristic in zip(certificate["results"], greedy["results"]):
        removed = tuple(heuristic["removed_edge_ids"])
        if removed not in replayed:
            actual = auditor.replay(disease_id, compound_id, list(removed))
            _require(actual["focus"] == heuristic["focus"], "Greedy witness replay mismatch")
            replayed.add(removed)
        supported = heuristic["focus"]["supported"]
        rank = heuristic["focus"]["rank"]
        _require(
            (supported and rank <= exact["worst_supported_rank"])
            or (not supported and exact["unsupported_attainable"]),
            "Greedy outcome exceeds the allegedly exact bound",
        )
        global_failure = not exact["top_k_robust"]
        greedy_failure = not supported or rank > top_k
        _require(not greedy_failure or global_failure, "Greedy failure absent from global bound")
        if exact["budget"] <= 1:
            _require(global_failure == greedy_failure, "Exhaustive greedy singleton inconsistency")
        results.append(
            {
                "supported": supported,
                "rank": rank,
                "failure_found": greedy_failure,
                "supported_rank_gap": exact["worst_supported_rank"] - rank if supported else None,
                "witness_edge_ids": list(removed),
            }
        )
    return results, len(replayed)


def _measure_query(auditor, disease_id, compound_id, top_k):
    started = time.perf_counter()
    certificate = auditor.audit(disease_id, compound_id, top_k=top_k, budget=2)
    audit_seconds = time.perf_counter() - started
    verified = auditor.verify(certificate)
    _require(verified["valid"], f"Certificate verification failed: {verified['errors']}")
    greedy, replayed = _check_greedy(auditor, certificate, score_tiebreak=False)
    strong, strong_replayed = _check_greedy(auditor, certificate, score_tiebreak=True)
    results = []
    for index, exact in enumerate(certificate["results"]):
        local_failure = exact["focus_only_unsupported_attainable"] or (
            exact["focus_only_worst_rank"] is None or exact["focus_only_worst_rank"] > top_k
        )
        _require(
            not local_failure or not exact["top_k_robust"], "Local failure absent from global bound"
        )
        results.append(
            {
                "budget": exact["budget"],
                "worst_supported_rank": exact["worst_supported_rank"],
                "unsupported_attainable": exact["unsupported_attainable"],
                "global_failure": not exact["top_k_robust"],
                "focus_only_worst_rank": exact["focus_only_worst_rank"],
                "focus_only_failure": local_failure,
                "competitor_rank_gap": exact["competitor_rank_gap"],
                **{f"greedy_{key}": value for key, value in greedy[index].items()},
                **{f"strong_greedy_{key}": value for key, value in strong[index].items()},
                "rank_witness_edge_ids": exact["rank_witness"]["removed_edge_ids"],
                "unsupported_witness_edge_ids": (
                    exact["unsupported_witness"]["removed_edge_ids"]
                    if exact["unsupported_witness"]
                    else None
                ),
                "rank_witness_focus_unchanged": all(
                    row["role"] != "focus" for row in exact["rank_witness"]["changed_compounds"]
                ),
            }
        )
    return (
        {
            "disease_id": disease_id,
            "compound_id": compound_id,
            "baseline_rank": certificate["baseline"]["rank"],
            "baseline_score": certificate["baseline"]["score"],
            "baseline_path_count": certificate["baseline"]["evidence_count"],
            "minimum_failure_budget": certificate["minimum_failure_budget"],
            "certificate_sha256": certificate["certificate_sha256"],
            "results": results,
            "certificate_witnesses_replayed": verified["replayed_witnesses"],
            "greedy_witnesses_replayed": replayed,
            "strong_greedy_witnesses_replayed": strong_replayed,
            "audit_seconds_cached": audit_seconds,
        },
        certificate,
    )


def _aggregate(rows):
    result = []
    for budget in range(3):
        values = [row["results"][budget] for row in rows]
        result.append(
            {
                "budget": budget,
                "candidate_queries": len(values),
                "globally_fragile": sum(row["global_failure"] for row in values),
                "globally_robust": sum(not row["global_failure"] for row in values),
                "unsupported_attainable": sum(row["unsupported_attainable"] for row in values),
                "focus_only_fragile": sum(row["focus_only_failure"] for row in values),
                "focus_only_false_robust_conclusions": sum(
                    row["global_failure"] and not row["focus_only_failure"] for row in values
                ),
                "global_rank_exceeds_focus_only": sum(
                    row["competitor_rank_gap"] > 0 for row in values
                ),
                "maximum_competitor_rank_gap": max(
                    (row["competitor_rank_gap"] for row in values), default=0
                ),
                "greedy_failures_found": sum(row["greedy_failure_found"] for row in values),
                "greedy_missed_failures": sum(
                    row["global_failure"] and not row["greedy_failure_found"] for row in values
                ),
                "greedy_supported_rank_suboptimal": sum(
                    row["greedy_supported_rank_gap"] is not None
                    and row["greedy_supported_rank_gap"] > 0
                    for row in values
                ),
                "strong_greedy_failures_found": sum(
                    row["strong_greedy_failure_found"] for row in values
                ),
                "strong_greedy_missed_failures": sum(
                    row["global_failure"] and not row["strong_greedy_failure_found"]
                    for row in values
                ),
                "strong_greedy_supported_rank_suboptimal": sum(
                    row["strong_greedy_supported_rank_gap"] is not None
                    and row["strong_greedy_supported_rank_gap"] > 0
                    for row in values
                ),
            }
        )
    return result


def _consider_examples(examples, measured, certificate):
    """Select extrema by a declared rule and retain zero-effect outcomes honestly."""
    criteria = {
        "largest_competitor_rank_gap": max(
            row["competitor_rank_gap"] for row in measured["results"]
        ),
        "largest_greedy_supported_rank_gap": max(
            (row["greedy_supported_rank_gap"] or 0 for row in measured["results"]), default=0
        ),
        "largest_strong_greedy_supported_rank_gap": max(
            (row["strong_greedy_supported_rank_gap"] or 0 for row in measured["results"]), default=0
        ),
        "scope_verdict_difference": int(
            any(
                row["global_failure"] and not row["focus_only_failure"]
                for row in measured["results"]
            )
        ),
    }
    for name, value in criteria.items():
        previous = examples.get(name)
        earlier_id = previous is not None and (
            certificate["disease"]["id"],
            certificate["compound"]["id"],
        ) < (previous["certificate"]["disease"]["id"], previous["certificate"]["compound"]["id"])
        if (
            previous is None
            or value > previous["selection_value"]
            or (value == previous["selection_value"] and earlier_id)
        ):
            examples[name] = {
                "selection_value": value,
                "selection_status": (
                    "positive_gap_observed" if value > 0 else "no_positive_gap_observed"
                ),
                "certificate": certificate,
            }


def run_benchmark(engine, *, progress=False):
    """Cover all diseases and baseline supported top-ten candidates without sampling."""
    started = time.perf_counter()
    auditor = BindingAuditor(engine)
    rows, disease_rows, examples = [], [], {}
    model_before = json.dumps(engine.model, sort_keys=True)
    old_scores = engine.score_matrix()
    numerical = _numerical_comparison(engine)
    for index, disease_id in enumerate(engine.entities["Disease"]):
        disease_started = time.perf_counter()
        candidates = auditor.baseline_candidates(disease_id, limit=10)
        disease_results = []
        for candidate in candidates:
            measured, certificate = _measure_query(auditor, disease_id, candidate["id"], 10)
            rows.append(measured)
            disease_results.append(measured)
            _consider_examples(examples, measured, certificate)
        disease_rows.append(
            {
                "disease_id": disease_id,
                "name": engine.nodes[disease_id]["name"],
                "status": "evaluated" if candidates else "no_supported_candidates",
                "candidate_queries": len(candidates),
                "summary": _aggregate(disease_results),
                "seconds": time.perf_counter() - disease_started,
            }
        )
        if progress and ((index + 1) % 10 == 0 or index + 1 == len(engine.entities["Disease"])):
            print(
                f"Audited {index + 1}/{len(engine.entities['Disease'])} diseases, "
                f"{len(rows)} candidates",
                flush=True,
            )
    _require(
        json.dumps(engine.model, sort_keys=True) == model_before, "Model changed during benchmark"
    )
    _require(
        np.array_equal(engine.score_matrix(), old_scores), "Legacy scores changed during benchmark"
    )
    expected = sum(row["candidate_queries"] for row in disease_rows)
    _require(len(rows) == expected, "Incomplete candidate benchmark")
    _require(len(disease_rows) == len(engine.entities["Disease"]), "Incomplete disease benchmark")
    return {
        "schema_version": "1.0",
        "title": "Global bounded BINDS evidence audit benchmark",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "source": _source_identity(),
        "identity": (
            next(iter(examples.values()))["certificate"]["identity"]
            if examples
            else {
                "dataset_sha256": engine.manifest.get("dataset_sha256"),
                "model_sha256": engine.model.get("model_sha256"),
            }
        ),
        "protocol": {
            "population": (
                "Every graph disease and its first ten supported candidates "
                "under the audit baseline scorer"
            ),
            "top_k": 10,
            "budgets": [0, 1, 2],
            "selection": (
                "No sampling or manual disease/candidate selection; "
                "IDs and score ties deterministic"
            ),
            "model": "Same saved model and scaler, no fitting; legacy scorer remains unchanged",
            "candidate_universe": len(engine.entities["Compound"]),
            "failure_scope": (
                "Any recorded BINDS edge anywhere in the graph; "
                "total edge deletions bounded by budget"
            ),
            "greedy": (
                "Every available next global edge evaluated; maximize current supported rank, "
                "unsupported preferred; lexicographic edge-ID ties; retain best prefix"
            ),
            "strong_greedy": (
                "Same exhaustive next-edge search, maximizing current rank after preferring "
                "unsupported; ties minimize focus score minus kth highest supported rival "
                "score, then focus score, then edge-ID. The rival threshold is recomputed "
                "after each edit. No kth rival means an infinite positive margin."
            ),
            "verification": (
                "All certificates receive same-algorithm optimality recheck and independent "
                "full-matrix witness replay; all greedy witnesses also replayed"
            ),
            "maximality_oracle": (
                "Independent literal-path exhaustive global-subset enumeration in "
                "tests/test_binding_audit.py, not full real-graph global enumeration"
            ),
            "examples": (
                "Largest observed competitor/greedy gap; first ID-ordered query wins ties; "
                "all results retained"
            ),
            "clinical_interpretation": (
                "Model fragility and algorithm correctness only; "
                "not clinical efficacy or experimental success"
            ),
        },
        "coverage": {
            "diseases_total": len(engine.entities["Disease"]),
            "diseases_processed": len(disease_rows),
            "diseases_without_supported_candidates": sum(
                row["status"] != "evaluated" for row in disease_rows
            ),
            "candidate_queries": len(rows),
            "budget_results": len(rows) * 3,
            "certificates_verified": len(rows),
            "certificate_witness_replay_checks": sum(
                row["certificate_witnesses_replayed"] for row in rows
            ),
            "greedy_witness_replay_checks": sum(row["greedy_witnesses_replayed"] for row in rows),
            "strong_greedy_witness_replay_checks": sum(
                row["strong_greedy_witnesses_replayed"] for row in rows
            ),
            "failed_checks": 0,
        },
        "summary": _aggregate(rows),
        "minimum_failure_budget_counts": dict(
            Counter(str(row["minimum_failure_budget"]) for row in rows)
        ),
        "numerical_comparison": numerical,
        "diseases": disease_rows,
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


def _report_status(output, status):
    """Invalidate every old success artifact before loading or running anything."""
    for path in (
        output,
        output.parent / "binding-audit-summary.json",
        *(output.parent / filename for filename in EXAMPLE_FILES.values()),
    ):
        write_json(path, status, pretty=True)


def _publish_reports(output, report):
    """Save the full measurement and small, directly verifiable release companions."""
    write_json(output, report, pretty=True)
    example_summaries = {}
    for name, filename in EXAMPLE_FILES.items():
        example = report["examples"].get(name)
        path = output.parent / filename
        if example is None:
            write_json(
                path,
                {"status": "unavailable", "reason": "No supported candidate queries"},
                pretty=True,
            )
            continue
        write_json(path, example["certificate"], pretty=True)
        example_summaries[name] = {
            "selection_status": example["selection_status"],
            "selection_value": example["selection_value"],
            "disease": example["certificate"]["disease"],
            "compound": example["certificate"]["compound"],
            "file": filename,
            "file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "certificate_sha256": example["certificate"]["certificate_sha256"],
        }
    keys = (
        "schema_version",
        "title",
        "executed_at",
        "status",
        "source",
        "identity",
        "protocol",
        "coverage",
        "summary",
        "minimum_failure_budget_counts",
        "numerical_comparison",
        "runtime_seconds",
        "environment",
    )
    summary = {key: report[key] for key in keys}
    summary.update(
        full_report={
            "file": output.name,
            "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        },
        examples=example_summaries,
    )
    write_json(output.parent / "binding-audit-summary.json", summary, pretty=True)


def main(argv=None):
    """Run the complete benchmark, failing the process on any inconsistency."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/v1.2.0/binding-audit-benchmark.json")
    )
    arguments = parser.parse_args(argv)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    _report_status(arguments.output, {"status": "running", "started_at": started_at})
    try:
        engine = GraphEngine(arguments.data_dir)
        result = run_benchmark(engine, progress=True)
        _publish_reports(arguments.output, result)
    except BaseException as error:
        _report_status(
            arguments.output,
            {
                "status": "failed",
                "started_at": started_at,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise
    print(
        json.dumps(
            {
                "status": result["status"],
                "coverage": result["coverage"],
                "summary": result["summary"],
                "seconds": result["runtime_seconds"],
                "output": str(arguments.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
