"""Compare mixed envelopes with literal complete-world sparse recomputation.

The default protocol is fixed before execution. Both methods share a loaded
GraphEngine, audit the same canonical top three, start with cold arithmetic
caches, and reuse work across those three focus compounds. Verification and
setup are reported separately from solving; no work-count ratio is a speedup.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import statistics
import subprocess
import time

import numpy as np
import scipy

from app import audit_numerics
from app.graph_engine import FEATURE_NAMES, GraphEngine
from app.mixed_audit import MixedAuditor
from scripts.benchmark_provenance import write_json

SIZES = (8, 16, 32, 64)
GROUP_COUNTS = (4, 8)
SEEDS = (101, 202, 303)
TRIALS = 3
CELLS = ((0, 0), (0, 1), (1, 0), (1, 1))
DISEASE = "Disease::synthetic"
TOP_K = 3
INPUT_FILES = ("graph.json", "model.json", "manifest.json", "evaluation.json")
SOURCE_FILES = (
    "app/audit_numerics.py",
    "app/binding_audit.py",
    "app/provenance_audit.py",
    "app/mixed_audit.py",
    "app/graph_engine.py",
    "scripts/benchmark_mixed_scaling.py",
    "scripts/benchmark_provenance.py",
)
REPORT_NAME = "mixed-scaling-benchmark.json"
SUMMARY_NAME = "mixed-scaling-summary.json"


def _require(condition, message):
    if not condition:
        raise RuntimeError(message)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        "file_sha256": {name: _hash(root / name) for name in SOURCE_FILES},
    }


def _clear_arithmetic_caches():
    # These are exactly the three bounded caches used by the declared scorer.
    # Resetting them gives neither method a warm-cache advantage from the other.
    for name in ("_log1p", "_sqrt", "_sigmoid"):
        getattr(audit_numerics, name).cache_clear()


def synthetic_inputs(compounds, groups, seed):
    """Create a deterministic graph with overlapping and missing source labels."""
    for value, lower, upper in ((compounds, 3, 1000), (groups, 1, 16), (seed, 0, 2**32 - 1)):
        if isinstance(value, bool) or not isinstance(value, int) or not lower <= value <= upper:
            raise ValueError("Invalid synthetic compounds, groups or seed")
    rng = np.random.Generator(np.random.PCG64(seed))
    nodes = []
    for label, count in (("Compound", compounds), ("Gene", 16), ("Pathway", 4)):
        nodes.extend(
            {
                "id": f"{label}::{index:04d}",
                "identifier": f"{index:04d}",
                "name": f"Synthetic {label.lower()} {index}",
                "label": label,
                "data": {},
            }
            for index in range(count)
        )
    nodes.append({"id": DISEASE, "name": "Synthetic disease", "label": "Disease", "data": {}})
    edges = []

    def edge(left, relation, right, sources=()):
        edges.append(
            {
                "id": f"edge::{len(edges):05d}",
                "source": left,
                "target": right,
                "type": relation,
                "sources": list(sources),
                "license": "CC0",
                "data": {},
            }
        )

    for compound in range(compounds):
        for gene in sorted(rng.choice(16, size=4, replace=False).tolist()):
            ordinal = len(edges)
            labels = [] if ordinal % 7 == 0 else [f"Synthetic source {ordinal % groups:02d}"]
            if labels and ordinal % 5 == 0 and groups > 1:
                labels.append(f"Synthetic source {(ordinal + 1) % groups:02d}")
            edge(f"Compound::{compound:04d}", "BINDS", f"Gene::{gene:04d}", labels)
    for gene in sorted(rng.choice(16, size=8, replace=False).tolist()):
        edge(DISEASE, "ASSOCIATES", f"Gene::{gene:04d}")
    interactions = {tuple(sorted((gene, (gene + 1) % 16))) for gene in range(16)}
    interactions.update(
        tuple(sorted(rng.choice(16, size=2, replace=False).tolist())) for _ in range(8)
    )
    for left, right in sorted(interactions):
        edge(f"Gene::{left:04d}", "INTERACTS", f"Gene::{right:04d}")
    for gene in range(16):
        memberships = {gene % 4}
        if rng.random() < 0.3:
            memberships.add(int(rng.integers(4)))
        for pathway in sorted(memberships):
            edge(f"Gene::{gene:04d}", "PARTICIPATES", f"Pathway::{pathway:04d}")
    specification = {"compounds": compounds, "source_groups": groups, "seed": seed}
    dataset_hash = hashlib.sha256(json.dumps(specification, sort_keys=True).encode()).hexdigest()
    graph = {
        "nodes": nodes,
        "edges": edges,
        "treatments": [],
        "metadata": {
            "dataset": "Synthetic mixed-audit scaling fixture",
            "dataset_sha256": dataset_hash,
        },
    }
    model = {
        "name": "Fixed synthetic signed coefficients; not trained or clinically validated",
        "dataset_sha256": dataset_hash,
        "feature_names": FEATURE_NAMES,
        "mean": rng.uniform(-0.3, 0.3, 8).tolist(),
        "scale": rng.uniform(0.5, 1.5, 8).tolist(),
        "coefficients": [0.8, -0.65, 0.35, 1.25, -0.9, 0.55, -0.4, 0.2],
        "intercept": -0.15,
    }
    model["model_sha256"] = hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    return graph, model, specification


def write_inputs(directory, compounds, groups, seed):
    """Retain the exact generated bytes, hashes and construction parameters."""
    directory.mkdir(parents=True, exist_ok=True)
    graph, model, specification = synthetic_inputs(compounds, groups, seed)
    write_json(directory / "graph.json", graph)
    write_json(directory / "model.json", model)
    write_json(
        directory / "manifest.json",
        {
            **graph["metadata"],
            "graph_sha256": _hash(directory / "graph.json"),
            "synthetic": specification,
        },
    )
    write_json(
        directory / "evaluation.json",
        {
            "status": "not_applicable",
            "reason": "Synthetic model; no training or efficacy evaluation",
        },
    )
    return {name: _hash(directory / name) for name in INPUT_FILES}


class NaiveReference:
    """Full sparse-path recomputation and reranking for each action representation.

    No envelope, contribution table, production rank helper, production replay,
    or per-world cache is used. Only the declared arithmetic kernel is shared.
    """

    def __init__(self, engine):
        self.engine = engine
        self.compounds = engine.entities["Compound"]
        self.coordinates = {}
        self.groups = {}
        for record in engine.edges.values():
            if record["type"] != "BINDS":
                continue
            self.coordinates[record["id"]] = (
                engine.positions["Compound"][record["source"]],
                engine.positions["Gene"][record["target"]],
            )
            for label in record["sources"]:
                self.groups.setdefault(f"source:{label}", set()).add(record["id"])

    def state(self, removed, foci=None):
        """Rebuild all three complete path products and all candidate ranks."""
        bindings = self.engine.matrices["BINDS"].tolil(copy=True)
        for edge_id in removed:
            bindings[self.coordinates[edge_id]] = 0
        bindings = bindings.tocsr()
        bindings.eliminate_zeros()
        associations = self.engine.matrices["ASSOCIATES"]
        interactions = self.engine.matrices["INTERACTS"]
        pathways = self.engine.matrices["PARTICIPATES"]
        direct = (bindings @ associations.T).toarray()[:, 0]
        interaction = ((bindings @ interactions) @ associations.T).toarray()[:, 0]
        pathway = ((bindings @ pathways) @ (associations @ pathways).T).toarray()[:, 0]
        repeats = (
            bindings.multiply(np.asarray(pathways.sum(axis=1)).ravel()) @ associations.T
        ).toarray()[:, 0]
        counts = np.stack((direct, interaction, pathway - repeats), axis=-1)
        scores, logits = audit_numerics.canonical_scores(
            counts,
            np.asarray(bindings.sum(axis=1)).ravel(),
            int(associations.sum()),
            self.engine.model,
        )
        order = sorted(
            (index for index in range(len(self.compounds)) if sum(counts[index]) > 0),
            key=lambda index: (-float(scores[index]), self.compounds[index]),
        )
        ranks = {index: rank for rank, index in enumerate(order, start=1)}
        return {
            compound: {
                "supported": index in ranks,
                "rank": ranks.get(index),
                "score": float(scores[index]),
                "logit": float(logits[index]),
                "counts": dict(zip(("direct", "interaction", "pathway"), map(int, counts[index]))),
                "evidence_count": int(sum(counts[index])),
            }
            for index, compound in enumerate(self.compounds)
            if foci is None or compound in foci
        }

    def actions(self):
        """Include no-op, single axes, overlap and only surviving residual records."""
        edges = set(self.coordinates)
        for selected in ((), *((key,) for key in sorted(self.groups))):
            grouped = self.groups[selected[0]] if selected else set()
            for residual in ((), *((key,) for key in sorted(edges - grouped))):
                yield selected, residual, grouped | set(residual)

    def solve(self, foci):
        """Share each complete-world rerank across all three audited compounds."""
        results = {
            compound: {
                cell: {
                    "worst_supported_rank": None,
                    "unsupported_attainable": False,
                    "covered_action_representations": 0,
                }
                for cell in CELLS
            }
            for compound in foci
        }
        worlds = 0
        for selected, residual, removed in self.actions():
            states = self.state(removed, foci)
            worlds += 1
            for cell in CELLS:
                if len(selected) > cell[0] or len(residual) > cell[1]:
                    continue
                for compound in foci:
                    row, focus = results[compound][cell], states[compound]
                    row["covered_action_representations"] += 1
                    if focus["supported"]:
                        row["worst_supported_rank"] = max(
                            row["worst_supported_rank"] or 0, focus["rank"]
                        )
                    else:
                        row["unsupported_attainable"] = True
        for cells in results.values():
            for row in cells.values():
                row["robust"] = (
                    not row["unsupported_attainable"]
                    and row["worst_supported_rank"] is not None
                    and row["worst_supported_rank"] <= TOP_K
                )
        return results, worlds


def compare_and_verify(engine, foci, certificates, reference):
    """Check every frontier cell, seal and witness with independent full products."""
    auditor, matrix = MixedAuditor(engine), NaiveReference(engine)
    checked, witness_count = 0, 0
    baseline = matrix.state(())
    for compound, certificate in zip(foci, certificates, strict=True):
        _require(certificate["compound"]["id"] == compound, "Focus identity mismatch")
        _require(certificate["baseline"] == baseline[compound], "Baseline state mismatch")
        _require(
            [(row["group_budget"], row["edge_budget"]) for row in certificate["results"]]
            == list(CELLS),
            "Incomplete exact frontier",
        )
        for row in certificate["results"]:
            cell = row["group_budget"], row["edge_budget"]
            _require(
                {key: row[key] for key in reference[compound][cell]} == reference[compound][cell],
                "Exhaustive frontier mismatch",
            )
            checked += 1
            for name in ("rank_witness", "unsupported_witness"):
                witness = row[name]
                if witness is None:
                    continue
                selected, residual = witness["group_ids"], witness["residual_edge_ids"]
                _require(
                    len(selected) <= cell[0] and len(residual) <= cell[1],
                    "Witness exceeds cell budget",
                )
                grouped = matrix.groups[selected[0]] if selected else set()
                _require(not grouped.intersection(residual), "Residual record did not survive")
                state = matrix.state(grouped | set(residual))[compound]
                _require(
                    witness["focus"] == {"before": baseline[compound], "after": state},
                    "Independent witness replay mismatch",
                )
                witness_count += 1
        verified = auditor.verify(certificate)
        _require(verified["valid"], f"Certificate verifier rejected: {verified['errors']}")
    return {
        "frontier_cells": checked,
        "certificates": len(certificates),
        "literal_matrix_witness_replays": witness_count,
    }


def _timed_method(engine, foci, method):
    _clear_arithmetic_caches()
    started = time.perf_counter()
    solver = MixedAuditor(engine) if method == "envelope" else NaiveReference(engine)
    setup = time.perf_counter() - started
    started = time.perf_counter()
    result = (
        [solver.audit(DISEASE, compound, top_k=TOP_K) for compound in foci]
        if method == "envelope"
        else solver.solve(foci)
    )
    return result, {"setup_seconds": setup, "solve_seconds": time.perf_counter() - started}


def _dataset(directory, compounds, groups, seed, trials, index):
    identity = write_inputs(directory, compounds, groups, seed)
    started = time.perf_counter()
    engine = GraphEngine(directory)
    load_seconds = time.perf_counter() - started
    started = time.perf_counter()
    baseline = NaiveReference(engine).state(())
    foci = sorted(
        (key for key, value in baseline.items() if value["supported"]),
        key=lambda key: baseline[key]["rank"],
    )[:TOP_K]
    _require(len(foci) == TOP_K, "Synthetic dataset lacks the predefined three supported foci")
    cohort_seconds = time.perf_counter() - started
    rows, first_certificates = [], None
    for trial in range(trials):
        order = ("envelope", "naive") if (index + trial) % 2 == 0 else ("naive", "envelope")
        outcomes, timings = {}, {}
        for method in order:
            outcomes[method], timings[method] = _timed_method(engine, foci, method)
        started = time.perf_counter()
        reference, worlds = outcomes["naive"]
        checked = compare_and_verify(engine, foci, outcomes["envelope"], reference)
        verification_seconds = time.perf_counter() - started
        certificates = outcomes["envelope"]
        seals = [certificate["certificate_sha256"] for certificate in certificates]
        if first_certificates is None:
            first_certificates = certificates
        else:
            _require(certificates == first_certificates, "Trial changed a certificate")
        rows.append(
            {
                "trial": trial + 1,
                "method_order": list(order),
                "timing": timings,
                "verification_seconds": verification_seconds,
                "checks": checked,
                "certificate_sha256": seals,
                "full_world_recomputations": worlds,
            }
        )
    _require(
        identity == {name: _hash(directory / name) for name in INPUT_FILES},
        "Synthetic input bytes changed",
    )
    return {
        "dataset_id": directory.name,
        "configuration": {"compounds": compounds, "source_groups": groups, "seed": seed},
        "input_file_sha256": identity,
        "shared_graph_engine_load_seconds": load_seconds,
        "shared_cohort_selection_seconds": cohort_seconds,
        "foci": foci,
        "binding_records": len([edge for edge in engine.edges.values() if edge["type"] == "BINDS"]),
        "certificates": first_certificates,
        "trials": rows,
    }


def aggregate(datasets):
    """Retain matched raw timings and summarize only measured workload ratios."""
    rows = []
    configurations = sorted(
        {
            (row["configuration"]["compounds"], row["configuration"]["source_groups"])
            for row in datasets
        }
    )
    for compounds, groups in configurations:
        trials = [
            trial
            for row in datasets
            if (row["configuration"]["compounds"], row["configuration"]["source_groups"])
            == (compounds, groups)
            for trial in row["trials"]
        ]
        medians = {
            method: {
                key: statistics.median(trial["timing"][method][key] for trial in trials)
                for key in ("setup_seconds", "solve_seconds")
            }
            for method in ("envelope", "naive")
        }
        solve_ratios = [
            trial["timing"]["naive"]["solve_seconds"] / trial["timing"]["envelope"]["solve_seconds"]
            for trial in trials
        ]
        total_ratios = [
            sum(trial["timing"]["naive"].values()) / sum(trial["timing"]["envelope"].values())
            for trial in trials
        ]
        rows.append(
            {
                "compounds": compounds,
                "source_groups": groups,
                "trials": len(trials),
                "median_seconds": medians,
                "paired_naive_over_envelope_solve_ratio": {
                    "minimum": min(solve_ratios),
                    "median": statistics.median(solve_ratios),
                    "maximum": max(solve_ratios),
                },
                "paired_naive_over_envelope_setup_and_solve_ratio": {
                    "minimum": min(total_ratios),
                    "median": statistics.median(total_ratios),
                    "maximum": max(total_ratios),
                },
            }
        )
    return rows


def run_study(
    output_dir,
    *,
    sizes=SIZES,
    group_counts=GROUP_COUNTS,
    seeds=SEEDS,
    trials=TRIALS,
    require_clean=False,
    progress=False,
):
    """Execute every declared dataset/trial, retaining failures rather than filtering."""
    if isinstance(trials, bool) or not isinstance(trials, int) or trials < 1:
        raise ValueError("trials must be a positive integer")
    grid = list(itertools.product(sizes, group_counts, seeds))
    if not grid or len(set(grid)) != len(grid):
        raise ValueError("The study grid must be nonempty and contain no duplicates")
    source = _source_identity()
    if require_clean:
        _require(
            source["working_tree_dirty"] is False,
            "Measured execution requires a clean source checkpoint",
        )
    started = time.perf_counter()
    datasets = []
    for index, (compounds, groups, seed) in enumerate(grid):
        directory = output_dir / "inputs" / f"c{compounds:04d}-g{groups:02d}-s{seed}"
        datasets.append(_dataset(directory, compounds, groups, seed, trials, index))
        if progress:
            print(
                f"{index + 1}/{len(grid)} datasets; {trials} trials each; "
                "all frontier and witness checks passed",
                flush=True,
            )
    after = _source_identity()
    _require(source["file_sha256"] == after["file_sha256"], "Scaling scientific source changed")
    for dataset in datasets:
        directory = output_dir / "inputs" / dataset["dataset_id"]
        _require(
            dataset["input_file_sha256"] == {name: _hash(directory / name) for name in INPUT_FILES},
            "Retained synthetic input bytes changed",
        )
    checks = [trial["checks"] for dataset in datasets for trial in dataset["trials"]]
    return {
        "schema_version": "1.0",
        "title": "Synthetic mixed-audit scaling against exhaustive sparse recomputation",
        "status": "passed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "source_at_finish": after,
        "protocol": {
            "compounds": list(sizes),
            "source_groups": list(group_counts),
            "seeds": list(seeds),
            "trials_per_dataset": trials,
            "is_full_predeclared_grid": tuple(sizes) == SIZES
            and tuple(group_counts) == GROUP_COUNTS
            and tuple(seeds) == SEEDS
            and trials == TRIALS,
            "genes": 16,
            "pathways": 4,
            "diseases": 1,
            "bindings_per_compound": 4,
            "canonical_baseline_foci": TOP_K,
            "top_k": TOP_K,
            "generator": (
                "NumPy PCG64; signed fixed coefficients and seeded scaling; "
                "overlapping and missing source labels"
            ),
            "cache_policy": (
                "Clear all three scalar arithmetic caches before each method; fresh "
                "solver per method/trial; alternate method order by dataset index + trial"
            ),
            "workload": (
                "Both methods share one GraphEngine load and cohort. Each solves all four "
                "budget cells for the same three compounds. Naive shares each full-world "
                "rerank across all three; envelopes share all slices across all three."
            ),
            "timing": (
                "perf_counter wall seconds; setup, solve, shared load/cohort and independent "
                "verification are separate; ratios exclude verification and shared load/cohort"
            ),
            "independence": (
                "Naive independently recomputes full sparse path products and ranks in each "
                "world, without contribution tables, envelopes, production rank helpers or "
                "production replay; the finite arithmetic scorer is deliberately shared"
            ),
            "verification": (
                "All four frontier cells and action counts match exhaustive results; every "
                "certificate verifies; every emitted witness is independently recomputed "
                "by full sparse products"
            ),
            "limitations": (
                "Small synthetic graphs on one recorded runtime, fixed degrees and one "
                "disease; no claim about Hetionet-scale latency, asymptotic exponent, "
                "predictive accuracy or general graph neural networks; runtime ratios "
                "include Python and certificate serialization overhead. The reference is "
                "literal exhaustive recomputation, not the fastest possible exhaustive solver."
            ),
        },
        "coverage": {
            "datasets": len(datasets),
            "trials": len(checks),
            "certificates_verified": sum(row["certificates"] for row in checks),
            "frontier_cells_compared": sum(row["frontier_cells"] for row in checks),
            "literal_matrix_witness_replays": sum(
                row["literal_matrix_witness_replays"] for row in checks
            ),
            "failed_checks": 0,
        },
        "summary": aggregate(datasets),
        "datasets": datasets,
        "runtime_seconds": time.perf_counter() - started,
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
    }


def main(argv=None):
    """Publish success only after the entire fixed study and all checks complete."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("reports/v1.4.0/scaling"))
    parser.add_argument("--require-clean", action="store_true")
    arguments = parser.parse_args(argv)
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    paths = [arguments.output_dir / name for name in (REPORT_NAME, SUMMARY_NAME)]
    started_at = datetime.now(timezone.utc).isoformat()
    for path in paths:
        write_json(path, {"status": "running", "started_at": started_at})
    try:
        report = run_study(
            arguments.output_dir, require_clean=arguments.require_clean, progress=True
        )
        write_json(paths[0], report)
        summary = {key: value for key, value in report.items() if key != "datasets"}
        summary["full_report"] = {"file": REPORT_NAME, "sha256": _hash(paths[0])}
        write_json(paths[1], summary)
    except BaseException as error:
        for path in paths:
            write_json(
                path,
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
                "status": report["status"],
                "coverage": report["coverage"],
                "summary": report["summary"],
                "runtime_seconds": report["runtime_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
