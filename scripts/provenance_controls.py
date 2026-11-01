"""Post-selected size-matched random-withdrawal controls for two illustrations.

Each draw removes the same number of distinct BINDS records as the named group,
uniformly without replacement from all binding records. Draws are independent;
this is descriptive simulation, not a clinical null model or a preregistered test.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np

from app.binding_audit import canonical_scores, certificate_digest
from app.graph_engine import GraphEngine
from app.provenance_audit import ProvenanceAuditor
from scripts.benchmark_provenance import write_json

SEED = 20261101
DRAWS = 1000
CASES = (
    ("rheumatoid arthritis", "Marimastat", "source:DrugBank (target)"),
    ("Paget's disease of bone", "Crizotinib", "pubmed:22037378"),
)


def _digest(value):
    return certificate_digest({"value": value})


def _focus_state(counts, degrees, disease_degree, model, focus):
    scores, logits = canonical_scores(counts, degrees, disease_degree, model)
    supported = counts.sum(axis=1) > 0
    ahead = supported & (
        (scores > scores[focus]) | ((scores == scores[focus]) & (np.arange(len(scores)) < focus))
    )
    return {
        "supported": bool(supported[focus]),
        "rank": int(ahead.sum()) + 1 if supported[focus] else None,
        "score": float(scores[focus]),
        "logit": float(logits[focus]),
        "counts": dict(zip(("direct", "interaction", "pathway"), map(int, counts[focus]))),
        "evidence_count": int(counts[focus].sum()),
    }


def _matrix_focus(engine, disease_id, compound_id, removed):
    """A second path implementation: edit CSR and recompute matrix products."""
    bindings = engine.matrices["BINDS"].copy().tolil()
    for edge_id in removed:
        edge = engine.edges[edge_id]
        bindings[
            engine.positions["Compound"][edge["source"]], engine.positions["Gene"][edge["target"]]
        ] = 0
    bindings = bindings.tocsr()
    bindings.eliminate_zeros()
    association = engine.matrices["ASSOCIATES"].getrow(engine.positions["Disease"][disease_id]).T
    pathways = engine.matrices["PARTICIPATES"]
    direct = (bindings @ association).toarray().ravel()
    interaction = ((bindings @ engine.matrices["INTERACTS"]) @ association).toarray().ravel()
    shared = ((bindings @ pathways) @ (association.T @ pathways).T).toarray().ravel()
    repeated = (
        (bindings.multiply(np.asarray(pathways.sum(axis=1)).ravel()) @ association)
        .toarray()
        .ravel()
    )
    counts = np.column_stack((direct, interaction, shared - repeated)).astype(np.int64)
    return _focus_state(
        counts,
        np.asarray(bindings.sum(axis=1)).ravel(),
        association.sum(),
        engine.model,
        engine.positions["Compound"][compound_id],
    )


def _prepare(engine, disease_id, compound_id):
    records = sorted(edge["id"] for edge in engine.edges.values() if edge["type"] == "BINDS")
    coordinates = np.asarray(
        [
            (
                engine.positions["Compound"][engine.edges[key]["source"]],
                engine.positions["Gene"][engine.edges[key]["target"]],
            )
            for key in records
        ]
    )
    disease_index = engine.positions["Disease"][disease_id]
    association = engine.matrices["ASSOCIATES"].getrow(disease_index).toarray().ravel()
    pathways = engine.matrices["PARTICIPATES"]
    contributions = np.column_stack(
        (
            association,
            engine.matrices["INTERACTS"] @ association,
            pathways @ (pathways.T @ association)
            - np.asarray(pathways.sum(axis=1)).ravel() * association,
        )
    ).astype(np.int64)
    return {
        "records": records,
        "coordinates": coordinates,
        "contributions": contributions,
        "baseline": engine.path_counts[:, disease_index],
        "degrees": np.asarray(engine.matrices["BINDS"].sum(axis=1)).ravel(),
        "disease_degree": association.sum(),
        "focus": engine.positions["Compound"][compound_id],
    }


def _random_samples(engine, disease_id, compound_id, number, draws, seed):
    prepared = _prepare(engine, disease_id, compound_id)
    rng = np.random.Generator(np.random.PCG64(seed))
    samples, verification_sets = [], {}
    worst = (0, None)
    for index in range(draws):
        chosen = np.sort(rng.choice(len(prepared["records"]), size=number, replace=False))
        removed = [prepared["records"][position] for position in chosen]
        current, degrees = prepared["baseline"].copy(), prepared["degrees"].copy()
        selected = prepared["coordinates"][chosen]
        np.add.at(current, selected[:, 0], -prepared["contributions"][selected[:, 1]])
        np.add.at(degrees, selected[:, 0], -1)
        if np.any(current < 0) or np.any(degrees < 0):
            raise RuntimeError("Random-withdrawal count invariant failed")
        state = _focus_state(
            current, degrees, prepared["disease_degree"], engine.model, prepared["focus"]
        )
        samples.append(
            {
                "index": index,
                "removed_edge_count": number,
                "removed_edge_ids_sha256": _digest(removed),
                "focus_edges_removed": int((selected[:, 0] == prepared["focus"]).sum()),
                **state,
            }
        )
        if index in (0, draws - 1):
            verification_sets[index] = removed
        if state["rank"] is not None and state["rank"] > worst[0]:
            worst = (state["rank"], index)
            verification_sets["worst"] = removed
        if not state["supported"] and "unsupported" not in verification_sets:
            verification_sets["unsupported"] = (index, removed)
    checks = _check_samples(engine, disease_id, compound_id, samples, verification_sets, worst)
    return samples, checks, len(prepared["records"])


def _summary(samples, structured):
    supported_ranks = [sample["rank"] for sample in samples if sample["supported"]]
    threshold = structured["focus"]["rank"]
    at_least = sum(
        not sample["supported"] or (threshold is not None and sample["rank"] >= threshold)
        for sample in samples
    )
    failure_count = sum(not sample["supported"] or sample["rank"] > 10 for sample in samples)
    return {
        "supported_draws": len(supported_ranks),
        "unsupported_draws": len(samples) - len(supported_ranks),
        "top_ten_failure_draws": failure_count,
        "top_ten_failure_fraction": failure_count / len(samples),
        "at_least_as_adverse_as_group_draws": at_least,
        "at_least_as_adverse_as_group_fraction": at_least / len(samples),
        "supported_rank_quantiles": (
            {
                str(q): float(np.quantile(supported_ranks, q, method="linear"))
                for q in (0, 0.25, 0.5, 0.75, 0.95, 1)
            }
            if supported_ranks
            else None
        ),
        "focus_edges_removed_quantiles": {
            str(q): float(
                np.quantile(
                    [sample["focus_edges_removed"] for sample in samples], q, method="linear"
                )
            )
            for q in (0, 0.5, 1)
        },
    }


def _group_focus_count(engine, compound_id, group_id, replay):
    kind, label = group_id.split(":", 1)
    members = []
    for edge in engine.edges.values():
        annotations = (
            edge.get("sources", [])
            if kind == "source"
            else edge.get("data", {}).get("pubmed_ids", [])
        )
        if edge["type"] == "BINDS" and label in annotations:
            members.append(edge["id"])
    members.sort()
    if (
        len(members) != replay["removed_edge_count"]
        or _digest(members) != replay["removed_edge_ids_sha256"]
    ):
        raise RuntimeError("Structured group membership does not match the control size")
    return sum(engine.edges[key]["source"] == compound_id for key in members)


def simulate_case(engine, disease_id, compound_id, group_id, *, draws=DRAWS, seed=SEED):
    """Retain every draw's outcome and membership digest, with explicit null support."""
    for name, value, minimum in (("draws", draws, 1), ("seed", seed, 0)):
        if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")
    auditor = ProvenanceAuditor(engine)
    kind = group_id.split(":", 1)[0]
    certificate = auditor.audit(
        disease_id, compound_id, group_kind=kind, group_ids=[group_id], budget=1
    )
    group = auditor.replay(disease_id, compound_id, [group_id], kind)
    samples, checks, universe_size = _random_samples(
        engine, disease_id, compound_id, group["removed_edge_count"], draws, seed
    )
    if not auditor.verify(certificate)["valid"]:
        raise RuntimeError("Structured-group certificate failed verification")
    return {
        "disease": certificate["disease"],
        "compound": certificate["compound"],
        "identity": certificate["identity"],
        "group_id": group_id,
        "scope": {
            "random_universe": "all recorded BINDS edges",
            "universe_size": universe_size,
            "draws": draws,
            "removed_edges_per_draw": group["removed_edge_count"],
            "seed": seed,
            "rng": (
                "NumPy Generator PCG64; uniform choice without replacement within " "each draw"
            ),
            "replacement_between_draws": True,
            "top_k": 10,
        },
        "baseline": certificate["baseline"],
        "structured_group_outcome": group,
        "structured_focus_edges_removed": _group_focus_count(engine, compound_id, group_id, group),
        "summary": _summary(samples, group),
        "verification": {
            "status": "passed",
            "matrix_replay_checks": checks,
            "group_certificate_verified": True,
        },
        "samples": samples,
    }


def _check_samples(engine, disease_id, compound_id, samples, selected, worst):
    checks = {index: removed for index, removed in selected.items() if isinstance(index, int)}
    if "worst" in selected:
        checks[worst[1]] = selected["worst"]
    if "unsupported" in selected:
        index, removed = selected["unsupported"]
        checks[index] = removed
    for index, removed in checks.items():
        replay = _matrix_focus(engine, disease_id, compound_id, removed)
        if replay != {key: samples[index][key] for key in replay}:
            raise RuntimeError("Random control matrix replay mismatch")
    return len(checks)


def run_controls(engine, *, draws=DRAWS, seed=SEED):
    """Execute the two fixed post-selected illustrations without choosing good outcomes."""
    started = time.perf_counter()
    rows = []
    for index, (disease_name, compound_name, group_id) in enumerate(CASES):
        disease = next(
            (
                key
                for key in engine.entities["Disease"]
                if engine.nodes[key]["name"] == disease_name
            ),
            None,
        )
        compound = next(
            (
                key
                for key in engine.entities["Compound"]
                if engine.nodes[key]["name"] == compound_name
            ),
            None,
        )
        if disease is None or compound is None:
            raise ValueError("The fixed control illustrations require the prepared full dataset")
        rows.append(
            simulate_case(engine, disease, compound, group_id, draws=draws, seed=seed + index)
        )
    root = Path(__file__).resolve().parents[1]
    return {
        "schema_version": "1.0",
        "status": "passed",
        "title": "Post-selected size-matched uniform BINDS-withdrawal controls",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "protocol": {
            "selection": (
                "The two group illustrations were chosen after exploratory stress "
                "testing; these descriptive controls were specified afterward"
            ),
            "purpose": (
                "Separate withdrawal magnitude from the concentration of records "
                "in the named group for these illustrations only"
            ),
            "sampling": (
                "1000 draws per illustration by default; equal global "
                "distinct-record count; all candidate compounds reranked"
            ),
            "interpretation": (
                "Simulation fractions are not error probabilities, p-values, "
                "clinical validation, independent replication, or general evidence "
                "of group specificity"
            ),
            "tail_order": (
                "Unsupported is at least as adverse as every supported rank; if "
                "structured outcome is unsupported only unsupported draws qualify"
            ),
            "known_difference": (
                "Uniform controls match global deletion count, not "
                "compound-specific deletion counts or source/experiment "
                "dependencies"
            ),
        },
        "source": {
            "file_sha256": {
                name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                for name in (
                    "scripts/provenance_controls.py",
                    "app/binding_audit.py",
                    "app/provenance_audit.py",
                    "app/graph_engine.py",
                )
            }
        },
        "cases": rows,
        "runtime_seconds": time.perf_counter() - started,
        "environment": {"python": platform.python_version(), "numpy": np.__version__},
    }


def main(argv=None):
    """Run controls with guarded output and invalidate stale success before computing."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/v1.3.0/provenance-size-matched-controls.json")
    )
    arguments = parser.parse_args(argv)
    for name in ("graph.json", "model.json", "evaluation.json", "manifest.json"):
        source = arguments.data_dir / name
        if arguments.output.resolve() == source.resolve() or (
            arguments.output.exists() and source.exists() and arguments.output.samefile(source)
        ):
            raise ValueError("Controls output must not overwrite graph or model inputs")
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(arguments.output, {"status": "running"})
    try:
        report = run_controls(GraphEngine(arguments.data_dir))
        write_json(arguments.output, report)
    except BaseException as error:
        write_json(
            arguments.output,
            {"status": "failed", "error_type": type(error).__name__, "error": str(error)},
        )
        raise
    print(
        json.dumps(
            {
                "status": report["status"],
                "runtime_seconds": report["runtime_seconds"],
                "cases": [
                    {
                        "disease": case["disease"],
                        "compound": case["compound"],
                        "summary": case["summary"],
                    }
                    for case in report["cases"]
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
