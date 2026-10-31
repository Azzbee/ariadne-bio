"""Exact rank bounds under globally budgeted binding-record withdrawal.

The audit has its own declared, shape-independent float64 scorer. The legacy
GraphEngine and saved model are untouched. A binding edit affects only the
compound at its source, enabling exact local score envelopes and a globally
optimal allocation of the remaining deletion budget to competitor promotions.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import itertools
import json
import math
from threading import RLock

import numpy as np

# SciPy exposes this compiled ufunc dynamically; pylint cannot inspect it.
from scipy.special import expit  # pylint: disable=no-name-in-module

from app.graph_engine import FEATURE_NAMES

MAX_BUDGET = 2
MAX_SAFE_INTEGER = 2**53 - 1
SCORER = "float64-fixed-order-v1"
METHOD = "binding-envelope-v1"
COUNT_NAMES = ("direct", "interaction", "pathway")
INTERPRETATION = (
    "This is an exact finite-budget audit of this fixed model under withdrawal of any "
    "recorded BINDS edges, including edges of competing compounds. It is not a biological "
    "intervention or a probability of efficacy. Source labels are not independent studies. "
    "The audit uses its declared fixed-order float64 scorer and score/compound-ID ties; "
    "legacy BLAS scores can differ in the last floating-point bits. Exactness is relative "
    "to this binary64 numerical runtime; transcendental functions can differ across "
    "runtimes, and verification rejects numerical mismatches. A null worst supported "
    "rank means no supported scenario exists. Unsupported outcomes are reported separately. "
    "The guarantee does not cover other edge families, correlated source-group failures, "
    "new edges, model refitting, or deletion budgets above the requested limit."
)


def _json_numeric_semantics(value):
    """Normalize transport-equivalent JSON numbers without rounding binary64.

    This is a small specified encoding, not an implementation of standard JCS.
    JSON.parse/stringify changes integral floats and negative zero to integers.
    Every integer-valued number must be within JavaScript's exact integer range;
    all remaining finite binary64 values keep their exact round-trippable value.
    Booleans, strings and numbers remain different types.
    """
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, int):
        if abs(value) > MAX_SAFE_INTEGER:
            raise ValueError("Unsafe JSON integer in certificate")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Nonfinite JSON number in certificate")
        if value.is_integer():
            if abs(value) > MAX_SAFE_INTEGER:
                raise ValueError("Unsafe integer-valued JSON float in certificate")
            return int(value)
        return value
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("Certificate JSON object keys must be strings")
        return {key: _json_numeric_semantics(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_numeric_semantics(item) for item in value]
    raise TypeError("Unsupported certificate JSON value")


def _digest(value) -> str:
    """Hash JSON numeric semantics with sorted keys, compact ASCII-escaped encoding."""
    encoded = json.dumps(
        _json_numeric_semantics(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def certificate_digest(certificate) -> str:
    """Hash all fields except the seal using the declared JSON numeric semantics.

    Integral float/int and signed-zero differences normalize; finite nonintegral
    binary64 values are not rounded. Booleans remain booleans. Unsafe integers
    and integer-valued floats beyond 2**53-1 are rejected before sealing.
    """
    return _digest(
        {key: value for key, value in certificate.items() if key != "certificate_sha256"}
    )


def canonical_scores(counts, compound_degree, disease_degree, model) -> tuple:
    """Return scores/logits with exactly the same eight operations for every row.

    Each term is evaluated separately in feature order. There is no BLAS dot
    product, fused multiply-add, or shape-dependent reduction over features.
    The graph counts and endpoint degrees retain the legacy feature definition.
    """
    values = np.asarray(counts, dtype=np.float64)
    compound_degree, disease_degree = np.broadcast_arrays(
        np.asarray(compound_degree, dtype=np.float64),
        np.asarray(disease_degree, dtype=np.float64),
    )
    divisor = np.sqrt(np.maximum(compound_degree * disease_degree, np.float64(1)))
    terms = [np.log1p(values[..., index]) for index in range(3)]
    terms.extend(np.log1p(values[..., index] / divisor) for index in range(3))
    terms.extend((np.log1p(compound_degree), np.log1p(disease_degree)))
    logits = np.full(values.shape[:-1], model["intercept"], dtype=np.float64)
    for index, term in enumerate(terms):
        standardized = (term - model["mean"][index]) / model["scale"][index]
        contribution = model["coefficients"][index] * standardized
        logits = np.add(logits, contribution)
    return expit(logits), logits


def _ranks(scores: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """Rank supported rows; compound rows already follow namespace-qualified IDs."""
    supported = np.flatnonzero(counts.sum(axis=1) > 0)
    order = supported[np.lexsort((supported, -scores[supported]))]
    result = np.zeros(len(scores), dtype=np.int64)
    result[order] = np.arange(1, len(order) + 1)
    return result


@dataclass(frozen=True)
class _State:
    counts: np.ndarray
    scores: np.ndarray
    logits: np.ndarray
    ranks: np.ndarray


@dataclass(frozen=True)
class _Envelopes:
    disease_index: int
    contributions: np.ndarray
    baseline: _State
    minimum: np.ndarray
    maximum: np.ndarray
    minimum_witness: tuple
    maximum_witness: tuple
    unsupported_witness: tuple
    local_states: int
    bounds_sha256: str


@dataclass(frozen=True)
class _Bound:
    rank: int | None
    rank_edges: tuple | None
    unsupported_edges: tuple | None
    focus_rank: int | None


class BindingAuditor:
    """Immutable scientific audit with bounded, lock-protected disease caches."""

    def __init__(self, engine, cache_size: int = 4):
        if isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 1:
            raise ValueError("Audit cache size must be a positive integer")
        self.engine = engine
        self._lock = RLock()
        self._cache_size = cache_size
        self._cache = OrderedDict()
        self._verification_cache = OrderedDict()
        self._replay_cache = OrderedDict()
        self._model = self._validate_model(engine.model)
        self._matrices = {name: value.copy() for name, value in engine.matrices.items()}
        self._compounds = tuple(engine.entities["Compound"])
        self._compound_positions = dict(engine.positions["Compound"])
        self._compound_degrees = np.asarray(self._matrices["BINDS"].sum(axis=1)).ravel()
        self._pathway_degrees = np.asarray(self._matrices["PARTICIPATES"].sum(axis=1)).ravel()
        self._records, self._bindings = self._validate_bindings()
        self._edge_coordinates = {
            edge_id: (compound, gene)
            for compound, records in enumerate(self._bindings)
            for edge_id, gene in records
        }
        graph_bytes = (engine.data_dir / "graph.json").read_bytes()
        self._identity = {
            "dataset_sha256": engine.manifest.get("dataset_sha256"),
            "graph_sha256": hashlib.sha256(graph_bytes).hexdigest(),
            "model_sha256": engine.model.get("model_sha256")
            or hashlib.sha256(json.dumps(engine.model, sort_keys=True).encode()).hexdigest(),
            "scorer": SCORER,
        }

    @staticmethod
    def _validate_model(model):
        if model is None:
            raise RuntimeError("A fitted model is required for binding audits; run evaluate")
        if model.get("feature_names", FEATURE_NAMES) != FEATURE_NAMES:
            raise ValueError("Unsupported audit model feature definitions")
        result = {}
        for key in ("mean", "scale", "coefficients"):
            try:
                vector = np.asarray(model[key], dtype=np.float64)
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"Invalid audit model {key}") from error
            if vector.shape != (8,) or not np.isfinite(vector).all():
                raise ValueError(f"Invalid audit model {key}")
            result[key] = vector.copy()
        if np.any(result["scale"] <= 0):
            raise ValueError("Audit model scales must be positive")
        try:
            intercept = np.asarray(model["intercept"], dtype=np.float64)
            if intercept.shape != ():
                raise ValueError("Intercept must be scalar")
            result["intercept"] = np.float64(intercept)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Invalid audit model intercept") from error
        if not np.isfinite(result["intercept"]):
            raise ValueError("Invalid audit model intercept")
        return result

    def _validate_bindings(self):
        """Reject duplicate records even if GraphEngine's binary CSR collapsed them."""
        graph = json.loads((self.engine.data_dir / "graph.json").read_text(encoding="utf-8"))
        records, coordinates = {}, set()
        bindings = [[] for _ in self._compounds]
        all_ids = set()
        for edge in graph["edges"]:
            if edge["id"] in all_ids:
                raise ValueError("Duplicate graph edge ID prevents binding certification")
            all_ids.add(edge["id"])
            if edge != self.engine.edges.get(edge["id"]):
                raise ValueError("Graph records changed after the engine was loaded")
            if edge["type"] != "BINDS":
                continue
            coordinate = (edge["source"], edge["target"])
            if coordinate in coordinates:
                raise ValueError("Duplicate BINDS endpoints prevent binding certification")
            coordinates.add(coordinate)
            try:
                compound = self._compound_positions[edge["source"]]
                gene = self.engine.positions["Gene"][edge["target"]]
            except KeyError as error:
                raise ValueError("Invalid typed BINDS endpoints") from error
            records[edge["id"]] = deepcopy(edge)
            bindings[compound].append((edge["id"], gene))
            if self._matrices["BINDS"][compound, gene] != 1:
                raise ValueError("BINDS endpoints do not match the graph matrix")
        if len(records) != self._matrices["BINDS"].nnz:
            raise ValueError("BINDS records do not match the binary graph matrix")
        return records, tuple(tuple(sorted(rows)) for rows in bindings)

    def _resolve(self, disease_id, compound_id):
        resolved = []
        for identifier, label in ((disease_id, "Disease"), (compound_id, "Compound")):
            node = self.engine.nodes.get(identifier)
            if node is None or node["label"] != label:
                raise KeyError(f"Unknown {label.lower()}: {identifier}")
            resolved.append({"id": identifier, "name": node["name"]})
        return resolved[0], resolved[1], self._compound_positions[compound_id]

    @staticmethod
    def _validate_limits(top_k, budget):
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 1552:
            raise ValueError("Audit top_k must be an integer from 1 through 1552")
        if isinstance(budget, bool) or not isinstance(budget, int) or not 0 <= budget <= MAX_BUDGET:
            raise ValueError("Audit deletion budget must be an integer from 0 through 2")

    def _state(self, counts, degrees, disease_degree):
        scores, logits = canonical_scores(counts, degrees, disease_degree, self._model)
        return _State(counts, scores, logits, _ranks(scores, counts))

    def _local_layer(self, records, contributions, disease_degree, size):
        """Evaluate every local subset in one exact cardinality layer."""
        targets = np.asarray([gene for _, gene in records], dtype=np.int64)
        subsets = list(itertools.combinations(range(len(records)), size))
        positions = np.asarray(subsets, dtype=np.int64).reshape(len(subsets), size)
        counts = contributions[targets].sum(axis=0) - contributions[targets[positions]].sum(axis=1)
        scores, _ = canonical_scores(counts, len(records) - size, disease_degree, self._model)
        present = counts.sum(axis=1) > 0
        valid, missing = np.flatnonzero(present), np.flatnonzero(~present)

        def witness(index):
            return tuple(records[value][0] for value in subsets[index])

        low, high = (
            (int(valid[np.argmin(scores[valid])]), int(valid[np.argmax(scores[valid])]))
            if len(valid)
            else (None, None)
        )
        return (
            scores[low] if low is not None else np.nan,
            scores[high] if high is not None else np.nan,
            witness(low) if low is not None else None,
            witness(high) if high is not None else None,
            witness(int(missing[0])) if len(missing) else None,
            len(subsets),
        )

    def _local_envelopes(self, compound, contributions, disease_degree):
        records = self._bindings[compound]
        minimum, maximum = np.full(3, np.nan), np.full(3, np.nan)
        low, high, unsupported = [None] * 3, [None] * 3, [None] * 3
        evaluated = 0
        for size in range(min(MAX_BUDGET, len(records)) + 1):
            result = self._local_layer(records, contributions, disease_degree, size)
            minimum[size], maximum[size], low[size], high[size], unsupported[size] = result[:5]
            evaluated += result[5]
        return minimum, maximum, tuple(low), tuple(high), tuple(unsupported), evaluated

    def _build_envelopes(self, disease_id):
        disease_index = self.engine.positions["Disease"][disease_id]
        associations = self._matrices["ASSOCIATES"].getrow(disease_index).toarray().ravel()
        pathways = self._matrices["PARTICIPATES"]
        contributions = np.column_stack(
            (
                associations,
                self._matrices["INTERACTS"] @ associations,
                pathways @ (pathways.T @ associations) - self._pathway_degrees * associations,
            )
        ).astype(np.int64)
        if np.any(contributions < 0):
            raise ValueError("Negative simple-path contributions violate audit assumptions")
        baseline_counts = np.asarray(self._matrices["BINDS"] @ contributions, dtype=np.int64)
        if not np.array_equal(baseline_counts, self.engine.path_counts[:, disease_index]):
            raise ValueError("Audit contribution counts disagree with the original graph")
        baseline = self._state(baseline_counts, self._compound_degrees, associations.sum())
        minimum, maximum = np.full((len(self._compounds), 3), np.nan), np.full(
            (len(self._compounds), 3), np.nan
        )
        low, high, unsupported = [], [], []
        evaluated = 0
        for compound in range(len(self._compounds)):
            result = self._local_envelopes(compound, contributions, associations.sum())
            minimum[compound], maximum[compound] = result[:2]
            low.append(result[2])
            high.append(result[3])
            unsupported.append(result[4])
            evaluated += result[5]
        bounds = {
            "identity": self._identity,
            "disease_id": disease_id,
            "minimum": [[float(x) if np.isfinite(x) else None for x in row] for row in minimum],
            "maximum": [[float(x) if np.isfinite(x) else None for x in row] for row in maximum],
            "minimum_witness": low,
            "maximum_witness": high,
            "unsupported_witness": unsupported,
        }
        return _Envelopes(
            disease_index,
            contributions,
            baseline,
            minimum,
            maximum,
            tuple(low),
            tuple(high),
            tuple(unsupported),
            evaluated,
            _digest(bounds),
        )

    def _envelopes(self, disease_id, *, verification=False):
        """Recheck verification envelopes independently once per immutable cache entry."""
        cache = self._verification_cache if verification else self._cache
        with self._lock:
            if disease_id not in cache:
                cache[disease_id] = self._build_envelopes(disease_id)
                while len(cache) > self._cache_size:
                    cache.popitem(last=False)
            cache.move_to_end(disease_id)
            return cache[disease_id]

    @staticmethod
    def _ahead(scores, threshold, focus):
        indices = np.arange(len(scores))
        return (scores > threshold) | ((scores == threshold) & (indices < focus))

    def _promotions(self, envelopes, focus, threshold, budget):
        """Buy the cheapest unit-value promotions among disjoint competitor rows."""
        costs = np.full(len(self._compounds), MAX_BUDGET + 1, dtype=np.int64)
        for cost in range(budget + 1):
            ahead = self._ahead(envelopes.maximum[:, cost], threshold, focus)
            costs[ahead] = np.minimum(costs[ahead], cost)
        costs[focus] = MAX_BUDGET + 1
        local_rank = int(np.sum(costs == 0)) + 1
        choices = sorted(
            (int(costs[index]), index) for index in np.flatnonzero((costs > 0) & (costs <= budget))
        )
        removed, promoted = [], 0
        for cost, competitor in choices:
            if cost > budget:
                break
            removed.extend(envelopes.maximum_witness[competitor][cost])
            budget -= cost
            promoted += 1
        return local_rank + promoted, tuple(removed), local_rank

    def _bound(self, envelopes, focus, budget):
        best_rank, best_edges, focus_rank, missing = None, None, None, None
        for size in range(budget + 1):
            absent = envelopes.unsupported_witness[focus][size]
            if absent is not None and missing is None:
                missing = absent
            threshold = envelopes.minimum[focus, size]
            if not np.isfinite(threshold):
                continue
            focal_edges = envelopes.minimum_witness[focus][size]
            rank, rivals, local_rank = self._promotions(envelopes, focus, threshold, budget - size)
            focus_rank = local_rank if focus_rank is None else max(focus_rank, local_rank)
            edges = tuple(sorted(focal_edges + rivals))
            if best_rank is None:
                best_rank, best_edges = rank, edges
            elif (-rank, len(edges), edges) < (-best_rank, len(best_edges), best_edges):
                best_rank, best_edges = rank, edges
        return _Bound(best_rank, best_edges, missing, focus_rank)

    def _fast_state(self, envelopes, removed):
        counts = envelopes.baseline.counts.copy()
        degrees = self._compound_degrees.copy()
        for edge_id in removed:
            compound, gene = self._edge_coordinates[edge_id]
            counts[compound] -= envelopes.contributions[gene]
            degrees[compound] -= 1
        disease_degree = self._matrices["ASSOCIATES"].getrow(envelopes.disease_index).sum()
        return self._state(counts, degrees, disease_degree)

    @staticmethod
    def _summary(state, compound, *, full=False):
        rank = int(state.ranks[compound]) or None
        result = {
            "supported": rank is not None,
            "rank": rank,
            "score": float(state.scores[compound]),
        }
        if full:
            result.update(
                logit=float(state.logits[compound]),
                counts=dict(zip(COUNT_NAMES, map(int, state.counts[compound]))),
                evidence_count=int(state.counts[compound].sum()),
            )
        return result

    def _witness(self, envelopes, focus, removed):
        if removed is None:
            return None
        state = self._fast_state(envelopes, removed)
        changed = sorted({self._edge_coordinates[edge_id][0] for edge_id in removed})
        records = []
        for edge_id in removed:
            edge = deepcopy(self._records[edge_id])
            edge["source_name"] = self.engine.nodes[edge["source"]]["name"]
            edge["target_name"] = self.engine.nodes[edge["target"]]["name"]
            records.append(edge)
        return {
            "removed_edge_ids": list(removed),
            "removed_records": records,
            "deletions_used": len(removed),
            "focus": self._summary(state, focus, full=True),
            "changed_compounds": [
                {
                    "id": self._compounds[index],
                    "name": self.engine.nodes[self._compounds[index]]["name"],
                    "role": "focus" if index == focus else "competitor",
                    "before": self._summary(envelopes.baseline, index),
                    "after": self._summary(state, index),
                    "removed_edge_ids": [
                        edge_id
                        for edge_id in removed
                        if self._edge_coordinates[edge_id][0] == index
                    ],
                }
                for index in changed
            ],
        }

    def _certificate(self, disease, compound, focus, top_k, budget, envelopes):
        baseline = self._summary(envelopes.baseline, focus, full=True)
        legacy_scores = self.engine.score_matrix()[:, envelopes.disease_index]
        legacy_ranks = _ranks(legacy_scores, envelopes.baseline.counts)
        baseline.update(
            legacy_score=float(legacy_scores[focus]),
            legacy_rank=int(legacy_ranks[focus]) or None,
            score_difference=float(baseline["score"] - legacy_scores[focus]),
            rank_agrees_with_legacy=baseline["rank"] == (int(legacy_ranks[focus]) or None),
        )
        results = []
        for limit in range(budget + 1):
            bound = self._bound(envelopes, focus, limit)
            results.append(
                {
                    "budget": limit,
                    "worst_supported_rank": bound.rank,
                    "unsupported_attainable": bound.unsupported_edges is not None,
                    "top_k_robust": (
                        bound.unsupported_edges is None
                        and bound.rank is not None
                        and bound.rank <= top_k
                    ),
                    "focus_only_worst_rank": bound.focus_rank,
                    "focus_only_unsupported_attainable": bound.unsupported_edges is not None,
                    "competitor_rank_gap": (
                        bound.rank - bound.focus_rank if bound.rank is not None else None
                    ),
                    "rank_witness": self._witness(envelopes, focus, bound.rank_edges),
                    "unsupported_witness": self._witness(envelopes, focus, bound.unsupported_edges),
                }
            )
        failure = next((row["budget"] for row in results if not row["top_k_robust"]), None)
        result = {
            "schema_version": "1.0",
            "method": METHOD,
            "disease": disease,
            "compound": compound,
            "top_k": top_k,
            "budget": budget,
            "scope": {
                "relationship": "BINDS",
                "operation": "delete_record",
                "universe": "all_recorded_BINDS_edges",
                "eligible_edges": len(self._records),
                "candidate_count": len(self._compounds),
                "includes_competitor_changes": True,
            },
            "identity": deepcopy(self._identity),
            "baseline": baseline,
            "results": results,
            "minimum_failure_budget": failure,
            "robust_through_budget": (
                budget if failure is None else (failure - 1 if failure else None)
            ),
            "proof": {
                "local_states_evaluated": envelopes.local_states,
                "covered_global_states": sum(
                    math.comb(len(self._records), size)
                    for size in range(min(budget, len(self._records)) + 1)
                ),
                "envelope_bounds_sha256": envelopes.bounds_sha256,
                "search_budget": MAX_BUDGET,
            },
            "interpretation": INTERPRETATION,
        }
        result["certificate_sha256"] = certificate_digest(result)
        return result

    def audit(self, disease_id, compound_id, top_k=10, budget=2):
        """Certify every budget from zero through the requested global BINDS cap."""
        self._validate_limits(top_k, budget)
        disease, compound, focus = self._resolve(disease_id, compound_id)
        return self._certificate(
            disease, compound, focus, top_k, budget, self._envelopes(disease_id)
        )

    def baseline_candidates(self, disease_id, limit=10):
        """Expose the audit scorer's supported baseline for complete benchmarking."""
        self._validate_limits(limit, 0)
        disease = self.engine.nodes.get(disease_id)
        if disease is None or disease["label"] != "Disease":
            raise KeyError(f"Unknown disease: {disease_id}")
        baseline = self._envelopes(disease_id).baseline
        order = sorted(np.flatnonzero(baseline.ranks), key=lambda index: baseline.ranks[index])
        return [
            {
                "id": self._compounds[index],
                "name": self.engine.nodes[self._compounds[index]]["name"],
                **self._summary(baseline, index, full=True),
            }
            for index in order[:limit]
        ]

    @staticmethod
    def _next_margins(state, focus, owners, scores, supported, top_k):
        """Update the kth rival score after one row changes, including its support."""
        rivals = sorted(
            (int(index) for index in np.flatnonzero(state.ranks) if index != focus),
            key=lambda index: state.ranks[index],
        )
        positions = np.full(len(state.scores), len(state.scores) + 1, dtype=np.int64)
        positions[rivals] = np.arange(1, len(rivals) + 1)

        def boundary(position):
            if position == 0:
                return np.inf
            return state.scores[rivals[position - 1]] if position <= len(rivals) else -np.inf

        lower = np.where(positions[owners] <= top_k, boundary(top_k + 1), boundary(top_k))
        upper = np.where(positions[owners] < top_k, boundary(top_k), boundary(top_k - 1))
        replacement = np.where(supported, scores, -np.inf)
        thresholds = np.maximum(lower, np.minimum(replacement, upper))
        thresholds[owners == focus] = boundary(top_k)
        focal_scores = np.where(owners == focus, scores, state.scores[focus])
        return focal_scores - thresholds, focal_scores

    def _next_scores(self, envelopes, state, available, removed):
        """Score the one affected row for every possible next binding deletion."""
        coordinates = np.asarray([self._edge_coordinates[value] for value in available])
        owners, genes = coordinates[:, 0], coordinates[:, 1]
        counts = state.counts[owners] - envelopes.contributions[genes]
        degrees = self._compound_degrees.copy()
        for edge_id in removed:
            degrees[self._edge_coordinates[edge_id][0]] -= 1
        disease_degree = self._matrices["ASSOCIATES"].getrow(envelopes.disease_index).sum()
        scores, _ = canonical_scores(counts, degrees[owners] - 1, disease_degree, self._model)
        return owners, scores, counts.sum(axis=1) > 0

    def _next_ranks(self, state, focus, owners, scores, supported):
        """Compute exact focal ranks for all one-row edits without sorting each graph."""
        threshold = state.scores[focus]
        before = self._ahead(state.scores, threshold, focus) & (state.ranks > 0)
        after = supported & ((scores > threshold) | ((scores == threshold) & (owners < focus)))
        outcomes = state.ranks[focus] + after.astype(int) - before[owners].astype(int)
        for position in np.flatnonzero(owners == focus):
            if not supported[position]:
                outcomes[position] = len(self._compounds) + 1
            else:
                ahead = self._ahead(state.scores, scores[position], focus) & (state.ranks > 0)
                ahead[focus] = False
                outcomes[position] = int(ahead.sum()) + 1
        return outcomes

    def _greedy_step(self, envelopes, focus, removed, top_k, score_tiebreak):
        """Evaluate every next global single-edge edit, including rival promotions."""
        state = self._fast_state(envelopes, removed)
        available = sorted(self._records.keys() - set(removed))
        if not available or state.ranks[focus] == 0:
            return removed
        owners, scores, supported = self._next_scores(envelopes, state, available, removed)
        outcomes = self._next_ranks(state, focus, owners, scores, supported)
        if score_tiebreak:
            margins, focal_scores = self._next_margins(
                state, focus, owners, scores, supported, top_k
            )
            chosen_index = np.lexsort(
                (np.arange(len(available)), focal_scores, margins, -outcomes)
            )[0]
        else:
            chosen_index = np.argmax(outcomes)
        chosen = available[int(chosen_index)]
        return tuple(sorted((*removed, chosen)))

    def greedy(self, disease_id, compound_id, budget=2, *, score_tiebreak=False, top_k=10):
        """Return an explicitly heuristic global greedy baseline and best prefixes."""
        self._validate_limits(top_k, budget)
        _, _, focus = self._resolve(disease_id, compound_id)
        envelopes = self._envelopes(disease_id)
        removed, results = (), []
        baseline = self._summary(envelopes.baseline, focus, full=True)
        objective = len(self._compounds) + 1 if not baseline["supported"] else baseline["rank"]
        best = (objective, baseline, ())
        for limit in range(budget + 1):
            if limit:
                removed = self._greedy_step(envelopes, focus, removed, top_k, score_tiebreak)
            current = self._summary(self._fast_state(envelopes, removed), focus, full=True)
            value = len(self._compounds) + 1 if not current["supported"] else current["rank"]
            if value > best[0]:
                best = (value, current, removed)
            results.append({"budget": limit, "focus": best[1], "removed_edge_ids": list(best[2])})
        return {
            "method": (
                "global-rank-greedy; unsupported beats supported; ties minimize "
                "focus-score minus kth-supported-rival score, then focus-score, then edge-ID"
                if score_tiebreak
                else "global-rank-greedy; unsupported beats supported; lexicographic edge-ID ties"
            ),
            "guarantee": "Attainable witnesses only; no optimality or robustness guarantee",
            "results": deepcopy(results),
        }

    def _validate_removed(self, removed_edge_ids):
        if not isinstance(removed_edge_ids, (list, tuple)):
            raise ValueError("Removed edge IDs must be a list")
        if any(not isinstance(value, str) for value in removed_edge_ids):
            raise ValueError("Removed edge IDs must be strings")
        if len(set(removed_edge_ids)) != len(removed_edge_ids):
            raise ValueError("Duplicate removed edge IDs")
        if len(removed_edge_ids) > MAX_BUDGET:
            raise ValueError("Replay supports at most two BINDS deletions")
        if not set(removed_edge_ids) <= self._records.keys():
            raise ValueError("Unknown or non-BINDS removed edge")
        return tuple(sorted(removed_edge_ids))

    def _matrix_replay(self, disease_id, removed):
        """Rebuild products from edited CSR matrices, without envelope/count shortcuts."""
        key = (disease_id, removed)
        with self._lock:
            if key in self._replay_cache:
                self._replay_cache.move_to_end(key)
                return self._replay_cache[key]
        bindings = self._matrices["BINDS"].copy().tolil()
        for edge_id in removed:
            compound, gene = self._edge_coordinates[edge_id]
            bindings[compound, gene] = 0
        bindings = bindings.tocsr()
        bindings.eliminate_zeros()
        disease_index = self.engine.positions["Disease"][disease_id]
        associations = self._matrices["ASSOCIATES"].getrow(disease_index).T
        pathways = self._matrices["PARTICIPATES"]
        direct = (bindings @ associations).toarray().ravel()
        interaction = ((bindings @ self._matrices["INTERACTS"]) @ associations).toarray().ravel()
        shared = ((bindings @ pathways) @ (associations.T @ pathways).T).toarray().ravel()
        repeated = (bindings.multiply(self._pathway_degrees) @ associations).toarray().ravel()
        counts = np.column_stack((direct, interaction, shared - repeated)).astype(np.int64)
        degrees = np.asarray(bindings.sum(axis=1)).ravel()
        state = self._state(counts, degrees, associations.sum())
        with self._lock:
            self._replay_cache[key] = state
            while len(self._replay_cache) > 64:
                self._replay_cache.popitem(last=False)
        return state

    def replay(self, disease_id, compound_id, removed_edge_ids):
        """Independently replay a bounded witness through full sparse graph products."""
        _, _, focus = self._resolve(disease_id, compound_id)
        removed = self._validate_removed(removed_edge_ids)
        state = self._matrix_replay(disease_id, removed)
        return {
            "disease_id": disease_id,
            "compound_id": compound_id,
            "removed_edge_ids": list(removed),
            "focus": self._summary(state, focus, full=True),
            "supported_candidates": int(np.count_nonzero(state.ranks)),
            "verification_method": "edited CSR matrices and full sparse path products",
        }

    def verify(self, certificate):
        """Check all fields, recompute bounds, and independently replay every witness.

        Optimality uses the same proven envelope algorithm, in a separate bounded
        recomputation cache. Replay uses full matrix products. Exhaustive global
        enumeration on independent tiny graphs is the separate test-suite oracle.
        """
        checks, errors, replayed = [], [], 0
        try:
            if not isinstance(certificate, dict):
                raise ValueError("Certificate must be a JSON object")
            if certificate.get("certificate_sha256") != certificate_digest(certificate):
                raise ValueError("Certificate checksum does not match its contents")
            checks.append("Certificate content checksum matches")
            disease_id = certificate["disease"]["id"]
            compound_id = certificate["compound"]["id"]
            top_k, budget = certificate["top_k"], certificate["budget"]
            self._validate_limits(top_k, budget)
            disease, compound, focus = self._resolve(disease_id, compound_id)
            expected = self._certificate(
                disease,
                compound,
                focus,
                top_k,
                budget,
                self._envelopes(disease_id, verification=True),
            )
            if _digest(certificate) != _digest(expected):
                raise ValueError("Certificate fields disagree with recomputed exact bounds")
            checks.append("All fields and identities match recomputed global and focus-only bounds")
            replayed = self._replay_certificate(disease_id, compound_id, certificate["results"])
            checks.append("Every distinct witness matches independent full-matrix replay")
        except (KeyError, TypeError, ValueError, OverflowError, IndexError) as error:
            errors.append(str(error))
        return {
            "status": "invalid" if errors else "verified",
            "valid": not errors,
            "checks": checks,
            "errors": errors,
            "replayed_witnesses": replayed,
            "verification_method": (
                "Same-algorithm optimality recomputation cached by immutable disease/model/graph; "
                "independent edited-matrix replay of witnesses. Exhaustive tiny-graph maximality "
                "is established separately by the scientific test suite."
            ),
        }

    def _replay_certificate(self, disease_id, compound_id, results):
        """Check every distinct witness and every changed competitor's actual outcome."""
        seen = set()
        for result in results:
            for name in ("rank_witness", "unsupported_witness"):
                witness = result[name]
                if witness is None:
                    continue
                removed = tuple(witness["removed_edge_ids"])
                if removed in seen:
                    continue
                replay = self.replay(disease_id, compound_id, list(removed))
                if replay["focus"] != witness["focus"]:
                    raise ValueError("Independent full-matrix witness replay disagrees")
                state = self._matrix_replay(disease_id, removed)
                for changed in witness["changed_compounds"]:
                    index = self._compound_positions[changed["id"]]
                    if changed["after"] != self._summary(state, index):
                        raise ValueError("Independent full-matrix competitor replay disagrees")
                seen.add(removed)
        return len(seen)
