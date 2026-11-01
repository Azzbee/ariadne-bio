"""Benchmark exact correlated provenance audits over every disease's top ten.

The individual-edge comparison has a different uncertainty space. It measures
scope sensitivity, not a claim that one error budget is scientifically truer.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
import tempfile
from pathlib import Path
import platform
import subprocess
import time

import numpy as np
import scipy

from app.binding_audit import BindingAuditor
from app.graph_engine import GraphEngine
from app.provenance_audit import ProvenanceAuditor

REPORT_FILES = (
    "provenance-audit-summary.json",
    "provenance-audit-example-source.json",
    "provenance-audit-example-pubmed.json",
    "provenance-catalog.json",
)


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _source_identity():
    root = Path(__file__).resolve().parents[1]
    names = (
        "app/provenance_audit.py",
        "app/binding_audit.py",
        "app/graph_engine.py",
        "scripts/benchmark_provenance.py",
    )
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
            name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names
        },
    }


def _verified(auditor, certificate):
    verification = auditor.verify(certificate)
    _require(verification["valid"], f"Certificate verification failed: {verification['errors']}")
    return verification


def _query(auditor, bindings, disease_id, compound_id, top_k):
    certificate = auditor.audit(disease_id, compound_id, top_k=top_k)
    verification = _verified(auditor, certificate)
    individual = bindings.audit(disease_id, compound_id, top_k=top_k)
    _require(
        certificate["baseline"]["rank"] == individual["baseline"]["rank"],
        "Baseline rankings disagree",
    )
    _require(
        certificate["baseline"]["score"] == individual["baseline"]["score"],
        "Baseline scores disagree",
    )
    plan = certificate["protection_plan"]
    conditional = auditor.audit(
        disease_id, compound_id, top_k=top_k, protected_group_ids=plan["representative"]
    )
    _require(
        conditional["results"][2]["robust"], "Claimed optimal protection does not prevent failure"
    )
    greedy = auditor.greedy_protection(disease_id, compound_id, top_k=top_k)
    greedy_condition = auditor.audit(
        disease_id, compound_id, top_k=top_k, protected_group_ids=greedy["protected_group_ids"]
    )
    _require(greedy_condition["results"][2]["robust"], "Greedy protection is not feasible")
    gap = greedy["additional_group_count"] - plan["minimum_additional_groups"]
    _require(gap >= 0, "Greedy protection improves allegedly exact cardinality")
    results = []
    for grouped, edge in zip(certificate["results"], individual["results"]):
        results.append(
            {
                "budget": grouped["budget"],
                "scenario_count": grouped["scenario_count"],
                "worst_supported_rank": grouped["worst_supported_rank"],
                "unsupported_attainable": grouped["unsupported_attainable"],
                "robust": grouped["robust"],
                "rank_witness_group_ids": (
                    grouped["rank_witness"]["group_ids"] if grouped["rank_witness"] else None
                ),
                "unsupported_witness_group_ids": (
                    grouped["unsupported_witness"]["group_ids"]
                    if grouped["unsupported_witness"]
                    else None
                ),
                "individual_edge_robust": edge["top_k_robust"],
                "individual_edge_worst_supported_rank": edge["worst_supported_rank"],
                "individual_edge_unsupported_attainable": edge["unsupported_attainable"],
            }
        )
    row = {
        "disease_id": disease_id,
        "compound_id": compound_id,
        "baseline_rank": certificate["baseline"]["rank"],
        "baseline_score": certificate["baseline"]["score"],
        "certificate_sha256": certificate["certificate_sha256"],
        "certificate_witnesses_replayed": verification["replayed_witnesses"],
        "certificate_bytes": len(json.dumps(certificate, separators=(",", ":")).encode()),
        "results": results,
        "protection_plan": plan,
        "greedy_protection": greedy,
        "greedy_additional_group_gap": gap,
    }
    return row, certificate


def _aggregate(rows):
    summary = []
    for budget in range(3):
        results = [row["results"][budget] for row in rows]
        summary.append(
            {
                "budget": budget,
                "candidate_queries": len(rows),
                "robust": sum(row["robust"] for row in results),
                "fragile": sum(not row["robust"] for row in results),
                "unsupported_attainable": sum(row["unsupported_attainable"] for row in results),
                "individual_edge_robust": sum(row["individual_edge_robust"] for row in results),
                "individual_edge_robust_but_group_fragile": sum(
                    row["individual_edge_robust"] and not row["robust"] for row in results
                ),
                "individual_edge_fragile_but_group_robust": sum(
                    not row["individual_edge_robust"] and row["robust"] for row in results
                ),
            }
        )
    return summary


def _named_example(engine, auditor, bindings, disease_name, compound_name, **scope):
    disease = next(
        (key for key in engine.entities["Disease"] if engine.nodes[key]["name"] == disease_name),
        None,
    )
    compound = next(
        (key for key in engine.entities["Compound"] if engine.nodes[key]["name"] == compound_name),
        None,
    )
    if disease is None or compound is None:
        return {"status": "unavailable", "reason": "Named full-data illustration is absent"}
    certificate = auditor.audit(disease, compound, **scope)
    verification = _verified(auditor, certificate)
    edge = bindings.audit(disease, compound)
    protection = certificate["protection_plan"]["representative"]
    conditional = auditor.audit(disease, compound, protected_group_ids=protection, **scope)
    _require(conditional["results"][-1]["robust"], "Example protection failed its own exact audit")
    return {
        "status": "passed",
        "selection": (
            "Illustration chosen after exploratory v1.2-robust-cohort group stress "
            "testing; not independent validation"
        ),
        "certificate": certificate,
        "verification": verification,
        "individual_edge_budget_two": {
            key: edge["results"][2][key]
            for key in ("worst_supported_rank", "unsupported_attainable", "top_k_robust")
        },
        "conditional_protection_certificate": conditional,
        "conditional_verification": _verified(auditor, conditional),
    }


def run_benchmark(engine, *, top_k=10, progress=False):
    """Audit the entire declared cohort and retain favorable and unfavorable results."""
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
        raise ValueError("top_k must be an integer from 1 through 100")
    started = time.perf_counter()
    before_model = json.dumps(engine.model, sort_keys=True)
    before_scores = engine.score_matrix().copy()
    auditor, bindings = ProvenanceAuditor(engine), BindingAuditor(engine)
    catalog = auditor.catalog(limit=100)
    rows, diseases, identity = [], [], None
    for disease in engine.entities["Disease"]:
        candidates = bindings.baseline_candidates(disease, limit=top_k)
        disease_started = time.perf_counter()
        for candidate in candidates:
            row, certificate = _query(auditor, bindings, disease, candidate["id"], top_k)
            rows.append(row)
            identity = certificate["identity"]
        diseases.append(
            {
                "disease_id": disease,
                "name": engine.nodes[disease]["name"],
                "candidate_queries": len(candidates),
                "runtime_seconds": time.perf_counter() - disease_started,
            }
        )
        if progress:
            print(
                (
                    f"{len(diseases)}/{len(engine.entities['Disease'])} diseases; "
                    f"{len(rows)} certificates verified"
                ),
                flush=True,
            )
    examples = {
        "source": _named_example(engine, auditor, bindings, "rheumatoid arthritis", "Marimastat"),
        "pubmed": _named_example(
            engine,
            auditor,
            bindings,
            "Paget's disease of bone",
            "Crizotinib",
            group_kind="pubmed",
            group_ids=["pubmed:22037378"],
        ),
    }
    _require(
        json.dumps(engine.model, sort_keys=True) == before_model, "Model changed during benchmark"
    )
    _require(
        np.array_equal(engine.score_matrix(), before_scores),
        "Legacy scores changed during benchmark",
    )
    _require(
        len(rows) == sum(disease["candidate_queries"] for disease in diseases),
        "Candidate coverage is incomplete",
    )
    pubmed_catalog = auditor.catalog("pubmed", limit=100)
    return {
        "schema_version": "1.0",
        "title": "Exact correlated provenance-group withdrawal benchmark",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "source": _source_identity(),
        "identity": identity or catalog["identity"],
        "protocol": {
            "population": (
                "Every graph disease and its canonical baseline " "supported top-k candidates"
            ),
            "top_k": top_k,
            "budgets": [0, 1, 2],
            "selected_groups": catalog["items"],
            "group_scope": (
                "Every observed BINDS provider label; exact at-most-two label subsets; "
                "all compounds jointly reranked"
            ),
            "withdrawal_semantics": (
                "Remove union of all BINDS records mentioning any withdrawn label; "
                "retain no independent-corroboration assumption"
            ),
            "comparison": (
                "Same model and cohort, individual-edge budgets 0..2; scopes differ, so "
                "differences are not failed v1.2 guarantees or clinical error rates"
            ),
            "protection": (
                "Exact minimum-cardinality additional group conditions; frequency-greedy "
                "baseline sees the same full failure family and removes redundant choices"
            ),
            "verification": (
                "Every certificate separately recomputed and distinct witnesses replayed "
                "with full sparse matrix edits; exact and greedy protection rerun "
                "for feasibility"
            ),
            "maximality_oracle": (
                "Independent literal-path and all-world enumeration on small graphs "
                "in tests/test_provenance_audit.py"
            ),
            "clinical_interpretation": (
                "Finite fixed-model sensitivity only; no efficacy, retraction, "
                "error probability or prospective savings claim"
            ),
        },
        "coverage": {
            "diseases_total": len(engine.entities["Disease"]),
            "diseases_processed": len(diseases),
            "diseases_without_supported_candidates": sum(
                row["candidate_queries"] == 0 for row in diseases
            ),
            "candidate_queries": len(rows),
            "budget_results": 3 * len(rows),
            "certificates_verified": len(rows),
            "witness_replay_checks": sum(row["certificate_witnesses_replayed"] for row in rows),
            "protection_feasibility_checks": 2 * len(rows),
            "failed_checks": 0,
            "source_group_count": catalog["total"],
            "distinct_source_scenarios_per_disease": 1
            + catalog["total"]
            + catalog["total"] * (catalog["total"] - 1) // 2,
            "max_certificate_bytes": max((row["certificate_bytes"] for row in rows), default=0),
        },
        "summary": _aggregate(rows),
        "protection_summary": {
            "minimum_group_count_histogram": dict(
                sorted(
                    Counter(
                        str(row["protection_plan"]["minimum_additional_groups"]) for row in rows
                    ).items()
                )
            ),
            "queries_with_multiple_optimal_plans": sum(
                row["protection_plan"]["optimal_set_count"] > 1 for row in rows
            ),
            "greedy_suboptimal_queries": sum(
                row["greedy_additional_group_gap"] > 0 for row in rows
            ),
            "maximum_greedy_group_gap": max(
                (row["greedy_additional_group_gap"] for row in rows), default=0
            ),
        },
        "catalog": {
            "source": catalog,
            "pubmed": pubmed_catalog,
            "pubmed_items_truncated": pubmed_catalog["total"] > len(pubmed_catalog["items"]),
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


def write_json(path, value, *, pretty=True):
    """Publish through a fresh temporary file, never a predictable .tmp symlink."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2 if pretty else None, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _outputs(output):
    return [output, *(output.parent / name for name in REPORT_FILES)]


def _guard_outputs(output, data_dir):
    protected = [
        data_dir / name for name in ("graph.json", "model.json", "manifest.json", "evaluation.json")
    ]
    outputs = _outputs(output)
    resolved = [path.resolve() for path in outputs]
    if len(set(resolved)) != len(resolved):
        raise ValueError("Benchmark outputs must be distinct")
    for destination in outputs:
        for source in protected:
            if destination.resolve() == source.resolve() or (
                destination.exists() and source.exists() and destination.samefile(source)
            ):
                raise ValueError("Benchmark output must not overwrite graph or model inputs")


def _status(output, status):
    for path in _outputs(output):
        write_json(path, status, pretty=True)


def _publish(output, report):
    write_json(output, report, pretty=True)
    for kind in ("source", "pubmed"):
        example = report["examples"][kind]
        write_json(
            output.parent / f"provenance-audit-example-{kind}.json",
            example.get("certificate", example),
            pretty=True,
        )
    write_json(output.parent / "provenance-catalog.json", report["catalog"], pretty=True)
    summary = {
        key: value
        for key, value in report.items()
        if key not in ("queries", "diseases", "examples", "catalog")
    }
    summary["full_report"] = {
        "file": output.name,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    summary["examples"] = {
        kind: {"file": f"provenance-audit-example-{kind}.json", "status": value["status"]}
        for kind, value in report["examples"].items()
    }
    write_json(output.parent / "provenance-audit-summary.json", summary, pretty=True)


def main(argv=None):
    """Run the complete benchmark and invalidate stale success on any failed attempt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/v1.3.0/provenance-audit-benchmark.json")
    )
    arguments = parser.parse_args(argv)
    _guard_outputs(arguments.output, arguments.data_dir)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    _status(arguments.output, {"status": "running", "started_at": started_at})
    try:
        report = run_benchmark(GraphEngine(arguments.data_dir), progress=True)
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
                    "protection_summary",
                    "runtime_seconds",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
