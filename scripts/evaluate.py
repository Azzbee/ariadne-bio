"""Fit and evaluate a leakage-controlled, reproducible treatment-link retriever."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import time

import numpy as np
import scipy

# SciPy exposes this compiled ufunc dynamically; pylint cannot inspect it.
from scipy.special import expit  # pylint: disable=no-name-in-module
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.graph_engine import FEATURE_NAMES, GraphEngine
from scripts.prepare_data import write_json


def split_pairs(pairs: list[tuple[str, str]], seed: int) -> dict:
    """Split sorted positive pairs before fitting transforms or model parameters."""
    ordered = sorted(pairs)
    permutation = np.random.default_rng(seed).permutation(len(ordered))
    train_end, validation_end = int(0.70 * len(ordered)), int(0.85 * len(ordered))
    return {
        "train": [ordered[index] for index in permutation[:train_end]],
        "validation": [ordered[index] for index in permutation[train_end:validation_end]],
        "test": [ordered[index] for index in permutation[validation_end:]],
    }


def sample_unobserved(engine: GraphEngine, train_pairs: list, seed: int, ratio: int = 10) -> list:
    """Sample disease-matched unobserved pairs, excluding every recorded treatment."""
    rng = np.random.default_rng(seed + 1)
    known = defaultdict(set)
    for compound, disease in engine.known_treatments:
        known[disease].add(compound)
    train_by_disease = defaultdict(int)
    for _, disease in train_pairs:
        train_by_disease[disease] += 1
    unobserved = []
    for disease in sorted(train_by_disease):
        candidates = [
            compound for compound in engine.entities["Compound"] if compound not in known[disease]
        ]
        count = min(len(candidates), train_by_disease[disease] * ratio)
        selected = rng.choice(len(candidates), size=count, replace=False)
        unobserved.extend((candidates[index], disease) for index in selected)
    return unobserved


def pair_features(engine: GraphEngine, matrix: np.ndarray, pairs: list) -> np.ndarray:
    """Extract only specified pairs from the evidence-derived feature tensor."""
    return np.asarray(
        [
            matrix[engine.positions["Compound"][compound], engine.positions["Disease"][disease]]
            for compound, disease in pairs
        ]
    )


def retrieval_metrics(
    engine: GraphEngine, scores: np.ndarray, pairs: list, masked_pairs: list
) -> tuple[dict, list]:
    """Rank full compound universes after masking only previously observed positives.

    Other positives in the same evaluation split remain candidates. Metrics are
    micro-averaged across held-out treatment links, with ID-based tie breaking.
    """
    masks = defaultdict(set)
    by_disease = defaultdict(list)
    for compound, disease in masked_pairs:
        masks[disease].add(compound)
    for compound, disease in pairs:
        by_disease[disease].append(compound)
    ranks = []
    examples = []
    for disease, positives in sorted(by_disease.items()):
        disease_index = engine.positions["Disease"][disease]
        candidates = [
            compound for compound in engine.entities["Compound"] if compound not in masks[disease]
        ]
        candidates.sort(
            key=lambda compound, disease_index=disease_index: (
                -scores[engine.positions["Compound"][compound], disease_index],
                compound,
            )
        )
        positions = {compound: rank for rank, compound in enumerate(candidates, start=1)}
        for compound in sorted(positives):
            rank = positions[compound]
            ranks.append(rank)
            examples.append(
                {
                    "compound_id": compound,
                    "compound": engine.nodes[compound]["name"],
                    "disease_id": disease,
                    "disease": engine.nodes[disease]["name"],
                    "rank": rank,
                    "candidate_count": len(candidates),
                    "score": float(scores[engine.positions["Compound"][compound], disease_index]),
                }
            )
    rank_values = np.asarray(ranks)
    return {
        "recall_at_10": float(np.mean(rank_values <= 10)),
        "mrr": float(np.mean(1.0 / rank_values)),
        "mean_rank": float(np.mean(rank_values)),
        "median_rank": float(np.median(rank_values)),
        "hits_at_10": int(np.sum(rank_values <= 10)),
        "evaluated_links": len(ranks),
        "evaluated_diseases": len(by_disease),
    }, examples


def train_model(engine: GraphEngine, split: dict, seed: int) -> tuple[dict, list]:
    """Fit the scaler on training examples and tune regularization on validation."""
    matrix = engine.feature_matrix()
    unobserved = sample_unobserved(engine, split["train"], seed)
    pairs = split["train"] + unobserved
    targets = np.concatenate((np.ones(len(split["train"])), np.zeros(len(unobserved))))
    training_features = pair_features(engine, matrix, pairs)
    scaler = StandardScaler().fit(training_features)
    features = scaler.transform(training_features)
    all_features = (matrix - scaler.mean_) / scaler.scale_
    candidates = []
    for regularization in (0.01, 0.1, 1.0, 10.0):
        fitted = LogisticRegression(
            C=regularization,
            max_iter=3000,
            random_state=seed,
            solver="lbfgs",
            class_weight="balanced",
        )
        fitted.fit(features, targets)
        scores = expit(all_features @ fitted.coef_[0] + fitted.intercept_[0])
        validation, _ = retrieval_metrics(engine, scores, split["validation"], split["train"])
        candidates.append((fitted, validation, regularization))
    fitted, validation, regularization = max(
        candidates, key=lambda result: (result[1]["mrr"], result[1]["recall_at_10"], -result[2])
    )
    model = {
        "name": "Typed-path logistic retrieval",
        "version": "1.0",
        "seed": seed,
        "feature_names": FEATURE_NAMES,
        "mean": scaler.mean_.tolist(),
        "scale": scaler.scale_.tolist(),
        "coefficients": fitted.coef_[0].tolist(),
        "intercept": float(fitted.intercept_[0]),
        "regularization_C": regularization,
        "training_positive_pairs": len(split["train"]),
        "training_unobserved_pairs": len(unobserved),
        "class_weight": "balanced",
        "negative_sampling_seed": seed + 1,
        "validation_metrics": validation,
        "selection": "Maximum validation MRR, then Recall@10, then stronger regularization",
        "validation_search": [{"C": value, **metrics} for _, metrics, value in candidates],
        "dataset_sha256": engine.manifest["dataset_sha256"],
        "interpretation": "Relative retrieval score; not calibrated clinical probability",
        "fit_scope": "Training split only; no refit on validation or test labels",
    }
    model["model_sha256"] = hashlib.sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    return model, unobserved


def cluster_bootstrap(ranks: list, seed: int, samples: int = 2000) -> dict:
    """Describe sampling uncertainty by resampling diseases, preserving link clusters."""
    by_disease = defaultdict(list)
    for row in ranks:
        by_disease[row["disease_id"]].append(row["rank"])
    clusters = [np.asarray(by_disease[disease]) for disease in sorted(by_disease)]
    rng = np.random.default_rng(seed + 2)
    estimates = []
    for _ in range(samples):
        selected = rng.integers(0, len(clusters), size=len(clusters))
        sampled_ranks = np.concatenate([clusters[index] for index in selected])
        estimates.append([np.mean(sampled_ranks <= 10), np.mean(1.0 / sampled_ranks)])
    intervals = np.quantile(np.asarray(estimates), [0.025, 0.975], axis=0)
    return {
        "recall_at_10_ci95": intervals[:, 0].tolist(),
        "mrr_ci95": intervals[:, 1].tolist(),
        "uncertainty": "Percentile bootstrap, diseases as clusters, 2,000 replicates",
    }


def compare_models(engine: GraphEngine, split: dict, seed: int) -> tuple[list, dict]:
    """Evaluate the fixed model and all baselines on exactly the same test universe."""
    counts = engine.path_counts
    degree = np.asarray(engine.matrices["BINDS"].sum(axis=1)).ravel()
    scores = {
        "Typed-path logistic": engine.score_matrix(),
        "Path count baseline": counts.sum(axis=-1).astype(float),
        "Target-degree baseline": np.broadcast_to(degree[:, None], counts.shape[:2]).astype(float),
        "Direct-overlap baseline": counts[..., 0].astype(float),
    }
    metrics, examples = [], {}
    masked = split["train"] + split["validation"]
    for name, values in scores.items():
        measured, ranks = retrieval_metrics(engine, values, split["test"], masked)
        metrics.append({"model": name, "name": name, **measured, **cluster_bootstrap(ranks, seed)})
        examples[name] = ranks
    return metrics, examples


def evaluate_ablations(engine: GraphEngine, split: dict) -> list:
    """Measure family removal without retraining the fitted model."""
    ablations = []
    for family in ("INTERACTS", "PARTICIPATES"):
        ablated_scores = engine.score_matrix((family,))
        measured, _ = retrieval_metrics(
            engine, ablated_scores, split["test"], split["train"] + split["validation"]
        )
        ablations.append({"excluded": [family], **measured})
    return ablations


def illustrative_examples(engine: GraphEngine, examples: dict) -> list:
    """Show best, median and worst outcomes; retain every outcome in the report."""
    model_ranks = sorted(
        examples["Typed-path logistic"],
        key=lambda item: (item["rank"], item["disease_id"], item["compound_id"]),
    )
    selected = [
        model_ranks[index] for index in sorted({0, len(model_ranks) // 2, len(model_ranks) - 1})
    ]
    for example in selected:
        example["outcome"] = "recovered_in_top_10" if example["rank"] <= 10 else "missed_top_10"
        example["features"] = engine.evidence(
            example["disease_id"], example["compound_id"], limit=1
        )["counts"]
    return selected


def run_evaluation(data_dir: Path, seed: int = 42) -> dict:
    """Execute model fitting, test evaluation, baseline comparison and ablations."""
    started = time.perf_counter()
    engine = GraphEngine(data_dir)
    split = split_pairs(list(engine.known_treatments), seed)
    model, unobserved = train_model(engine, split, seed)
    engine.model = model
    metrics, examples = compare_models(engine, split, seed)
    report = {
        "title": "Retrospective treatment-link retrieval",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": engine.manifest["dataset_sha256"],
        "model_sha256": model["model_sha256"],
        "seed": seed,
        "metrics": metrics,
        "ablations": evaluate_ablations(engine, split),
        "examples": illustrative_examples(engine, examples),
        "protocol": {
            "task": "Recover held-out recorded treatment links from biological evidence paths",
            "split_unit": "Compound–disease pair, shuffled with a fixed seed",
            "split_fractions": {"train": 0.70, "validation": 0.15, "test": 0.15},
            "graph": (
                "All evidence edges retained; TREATS and PALLIATES absent from all feature "
                "matrices and graph projections"
            ),
            "transductive": True,
            "candidate_universe": (
                f"All {len(engine.entities['Compound']):,} compounds, including compounds with no "
                "paths; mask train and validation positives for each test disease"
            ),
            "candidate_count": len(engine.entities["Compound"]),
            "ties": "Score descending, then namespace-qualified compound ID ascending",
            "multiple_positives": "Other test positives remain in the candidate ranking",
            "unobserved_sampling": (
                "Up to 10 disease-matched unobserved pairs per training positive, without "
                "replacement per disease; all recorded positives excluded"
            ),
            "negative_label_meaning": "Unobserved in this dataset, not established ineffective",
            "preprocessing": "StandardScaler fitted on training pairs only",
            "hyperparameters": "C in [0.01, 0.1, 1, 10], selected by validation MRR",
            "metrics": "Micro Recall@10 and mean reciprocal rank over held-out positive links",
            "ablation": (
                "Same saved coefficients and scaler; family removal changes exact counts "
                "and affected degrees"
            ),
            "uncertainty": (
                "95% percentile bootstrap intervals, 2,000 replicates; diseases resampled "
                "as clusters to preserve correlated links. Intervals describe this fixed split."
            ),
            "llm_role": "None in ranking, fitting, split selection, or evaluation",
        },
        "split": {
            "train": len(split["train"]),
            "validation": len(split["validation"]),
            "test": len(split["test"]),
            "total": len(engine.known_treatments),
            "unobserved_train": len(unobserved),
            "pair_ids": {key: [list(pair) for pair in pairs] for key, pairs in split.items()},
        },
        "feature_definitions": {
            "direct": "C-BINDS-G-ASSOCIATES-D; exact number of shared genes",
            "interaction": (
                "C-BINDS-G-INTERACTS-G-ASSOCIATES-D; symmetric interactions, distinct genes"
            ),
            "pathway": (
                "C-BINDS-G-PARTICIPATES-P-PARTICIPATES-G-ASSOCIATES-D; "
                "distinct genes, exact simple paths"
            ),
            "transformation": (
                "log1p(counts), log1p(counts/sqrt(binding_degree*association_degree)), "
                "log1p endpoint degrees"
            ),
        },
        "limitations": [
            "Retrospective recovery is not clinical efficacy validation or new drug discovery.",
            (
                "The evidence graph is historical and transductive; this is not a temporal "
                "or unseen-disease generalization test."
            ),
            (
                "Removing indication edges prevents direct graph leakage, but correlated "
                "literature curation can still encode prior medical knowledge."
            ),
            (
                "Unobserved pairs can contain real but undocumented treatments; retrieval "
                "scores are not calibrated probabilities."
            ),
            (
                "A single fixed split has sampling uncertainty. All test links and failures "
                "are retained in the report."
            ),
            (
                "Dense well-studied biology receives more coverage. Source relationships are "
                "consolidated observations, not independent studies."
            ),
            (
                "Evidence-family ablation measures model sensitivity, not causal biological "
                "interventions."
            ),
            (
                "Binding and association edges do not encode beneficial action direction, dose, "
                "safety, contraindications, or tissue specificity. High-ranking compounds can "
                "be medically inappropriate."
            ),
        ],
        "test_ranks": examples,
        "runtime_seconds": round(time.perf_counter() - started, 3),
        "environment": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "scikit_learn": sklearn.__version__,
        },
    }
    write_json(data_dir / "model.json", model, pretty=True)
    write_json(data_dir / "evaluation.json", report, pretty=True)
    return report


def main() -> None:
    """Run and summarize the experiment without substituting expected metrics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    report = run_evaluation(args.data_dir, args.seed)
    print(
        json.dumps(
            {
                "metrics": report["metrics"],
                "split": {
                    key: value for key, value in report["split"].items() if key != "pair_ids"
                },
                "runtime_seconds": report["runtime_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
