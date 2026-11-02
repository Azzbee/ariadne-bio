"""Exact conditional envelopes for one provenance group plus one residual record.

A source withdrawal changes several compound rows jointly. Conditional on that
withdrawal, a residual BINDS deletion changes one row; compound separability is
restored. Batched one-row scores therefore cover every permitted mixed action
without reranking the full graph for each of its individual records.
"""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
import json

import numpy as np

from app.audit_numerics import SCORER
from app.binding_audit import BindingAuditor, _Envelopes, _State, _ranks, certificate_digest
from app.provenance_audit import _annotation_ids

METHOD = "mixed-group-edge-envelope-v1"
MAX_GROUPS = 16
MAX_CERTIFICATE_BYTES = 256 * 1024
MAX_PREVIEW = 6
INTERPRETATION = (
    "Exact for the declared frozen ranker and the rectangular budget of at most "
    "one selected provenance-group withdrawal plus at most one residual BINDS "
    "record deletion. A group removes the union of all records carrying its "
    "imported annotation; a residual record must survive that withdrawal. All "
    "competing compounds change jointly. Group and record budgets are separate "
    "units, not equal amounts of evidence. Source labels are not independent "
    "suppliers, and a citation need not identify one experiment. This is an "
    "evidence-quarantine sensitivity analysis, not a factual retraction, clinical "
    "effect, error probability or new biological discovery. Exactness is relative "
    "to decimal80-binary64-v1. Unselected annotations, other relation families, "
    "larger budgets, new records and model refitting are outside scope."
)


def _digest(value):
    return certificate_digest({"value": value})


@dataclass(frozen=True)
class _ConditionalSlice:
    groups: tuple
    removed: tuple
    remaining: tuple
    positions: dict
    owners: np.ndarray
    scores: np.ndarray
    logits: np.ndarray
    counts: np.ndarray
    supported: np.ndarray
    envelopes: _Envelopes


@dataclass(frozen=True)
class _Slices:
    items: dict
    digest: str
    local_states: int


class MixedAuditor(BindingAuditor):
    """Reuse immutable validation and rank allocation, not legacy construction.

    The inherited input snapshot, finite scorer, unit-cost rank allocation and
    independent matrix replay have the same mathematical contracts. Mixed audit
    construction and certificate identities remain entirely separate.
    """

    def __init__(self, engine, cache_size=2):
        super().__init__(engine, cache_size, scorer=SCORER)
        groups = defaultdict(set)
        for edge_id, record in self._records.items():
            for group_id in _annotation_ids(record):
                groups[group_id].add(edge_id)
        self._groups = {key: tuple(sorted(rows)) for key, rows in sorted(groups.items())}
        self._identity["group_map_sha256"] = _digest(self._groups)
        self._ordered_edges = tuple(sorted(self._records))

    @staticmethod
    def _limits(top_k, group_budget, edge_budget):
        for name, value, minimum, maximum in (
            ("top_k", top_k, 1, 100),
            ("group_budget", group_budget, 0, 1),
            ("edge_budget", edge_budget, 0, 1),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"Mixed {name} must be an integer from {minimum} through {maximum}"
                )

    def _selection(self, kind, group_ids):
        if kind not in ("source", "pubmed"):
            raise ValueError("Group kind must be source or pubmed")
        if group_ids is None:
            if kind == "pubmed":
                raise ValueError("PubMed auditing requires an explicit selection of 1..16 groups")
            groups = tuple(key for key in self._groups if key.startswith("source:"))
        else:
            if (
                not isinstance(group_ids, (list, tuple))
                or not 1 <= len(group_ids) <= MAX_GROUPS
                or any(not isinstance(key, str) for key in group_ids)
            ):
                raise ValueError("Select 1..16 distinct provenance group IDs")
            if len(set(group_ids)) != len(group_ids):
                raise ValueError("Select distinct provenance group IDs")
            groups = tuple(sorted(group_ids))
        if len(groups) > MAX_GROUPS:
            raise ValueError("Select at most 16 provenance groups")
        if any(key not in self._groups or not key.startswith(f"{kind}:") for key in groups):
            raise ValueError("Unknown group ID or group kind mismatch")
        return groups

    def _metadata(self, key):
        members = self._groups[key]
        kind, label = key.split(":", 1)
        result = {
            "group_id": key,
            "label": label if kind == "source" else f"PubMed {label}",
            "edge_count": len(members),
            "compound_count": len({self._edge_coordinates[edge][0] for edge in members}),
            "edge_ids_sha256": _digest(members),
        }
        if kind == "pubmed":
            result["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{label}/"
        return result

    def _conditional(self, groups, contributions, disease_index, disease_degree):
        removed = self._groups[groups[0]] if groups else ()
        removed_set = set(removed)
        remaining = tuple(key for key in self._ordered_edges if key not in removed_set)
        coordinates = np.asarray(
            [self._edge_coordinates[key] for key in remaining], dtype=np.int64
        ).reshape(-1, 2)
        owners, genes = coordinates[:, 0], coordinates[:, 1]
        counts = np.zeros((len(self._compounds), 3), dtype=np.int64)
        degrees = np.zeros(len(self._compounds), dtype=np.int64)
        np.add.at(counts, owners, contributions[genes])
        np.add.at(degrees, owners, 1)
        baseline = self._state(counts, degrees, disease_degree)
        next_counts = counts[owners] - contributions[genes]
        scores, logits = self._score(next_counts, degrees[owners] - 1, disease_degree, self._model)
        supported = next_counts.sum(axis=1) > 0
        minimum = np.full((len(self._compounds), 2), np.nan)
        maximum = minimum.copy()
        baseline_supported = baseline.ranks > 0
        minimum[baseline_supported, 0] = baseline.scores[baseline_supported]
        maximum[baseline_supported, 0] = baseline.scores[baseline_supported]
        low, high, missing = [], [], []
        order = np.argsort(owners, kind="stable")
        splits = np.cumsum(np.bincount(owners, minlength=len(self._compounds)))
        begin = 0
        for compound, end in enumerate(splits):
            positions = order[begin:end]
            begin = end
            valid = positions[supported[positions]]
            absent = positions[~supported[positions]]
            base_witness = () if baseline_supported[compound] else None
            minimum_witness = maximum_witness = None
            if len(valid):
                smallest = int(valid[np.argmin(scores[valid])])
                largest = int(valid[np.argmax(scores[valid])])
                minimum[compound, 1] = scores[smallest]
                maximum[compound, 1] = scores[largest]
                minimum_witness, maximum_witness = (remaining[smallest],), (remaining[largest],)
            low.append((base_witness, minimum_witness))
            high.append((base_witness, maximum_witness))
            missing.append(
                (
                    None if baseline_supported[compound] else (),
                    (remaining[int(absent[0])],) if len(absent) else None,
                )
            )
        bounds = {
            "identity": self._identity,
            "disease_index": disease_index,
            "groups": groups,
            "minimum": [[float(x) if np.isfinite(x) else None for x in row] for row in minimum],
            "maximum": [[float(x) if np.isfinite(x) else None for x in row] for row in maximum],
            "minimum_witness": low,
            "maximum_witness": high,
            "unsupported_witness": missing,
        }
        envelopes = _Envelopes(
            disease_index,
            contributions,
            baseline,
            minimum,
            maximum,
            tuple(low),
            tuple(high),
            tuple(missing),
            len(self._compounds) + len(remaining),
            _digest(bounds),
        )
        return _ConditionalSlice(
            groups,
            removed,
            remaining,
            {key: index for index, key in enumerate(remaining)},
            owners,
            scores,
            logits,
            next_counts,
            supported,
            envelopes,
        )

    def _build_slices(self, disease_id, groups):
        disease_index = self._inputs.disease_positions[disease_id]
        association = self._matrices["ASSOCIATES"].getrow(disease_index).toarray().ravel()
        pathways = self._matrices["PARTICIPATES"]
        contributions = np.column_stack(
            (
                association,
                self._matrices["INTERACTS"] @ association,
                pathways @ (pathways.T @ association) - self._pathway_degrees * association,
            )
        ).astype(np.int64)
        if np.any(contributions < 0):
            raise ValueError("Negative path contributions violate mixed audit assumptions")
        items = {
            selected: self._conditional(selected, contributions, disease_index, association.sum())
            for selected in ((), *((key,) for key in groups))
        }
        if not np.array_equal(
            items[()].envelopes.baseline.counts, self._inputs.path_counts[:, disease_index]
        ):
            raise ValueError("Mixed contribution counts disagree with the original graph")
        return _Slices(
            items,
            _digest([(key, value.envelopes.bounds_sha256) for key, value in items.items()]),
            sum(value.envelopes.local_states for value in items.values()),
        )

    def _slices(self, disease_id, groups, *, verification=False):
        cache = self._verification_cache if verification else self._cache
        key = (disease_id, groups)
        with self._lock:
            if key not in cache:
                cache[key] = self._build_slices(disease_id, groups)
                while len(cache) > self._cache_size:
                    cache.popitem(last=False)
            cache.move_to_end(key)
            return cache[key]

    @staticmethod
    def _slice_state(conditional, residual):
        base = conditional.envelopes.baseline
        if not residual:
            return base
        position = conditional.positions[residual[0]]
        owner = conditional.owners[position]
        counts, scores, logits = base.counts.copy(), base.scores.copy(), base.logits.copy()
        counts[owner] = conditional.counts[position]
        scores[owner], logits[owner] = conditional.scores[position], conditional.logits[position]
        return _State(counts, scores, logits, _ranks(scores, counts))

    def _mixed_witness(self, slices, focus, choice):
        if choice is None:
            return None
        groups, residual = choice
        conditional = slices.items[groups]
        removed = tuple(sorted((*conditional.removed, *residual)))
        return {
            "group_ids": list(groups),
            "residual_edge_ids": list(residual),
            "removed_edge_count": len(removed),
            "removed_edge_ids_sha256": _digest(removed),
            "affected_compound_count": len({self._edge_coordinates[key][0] for key in removed}),
            "removed_edges_preview": [
                deepcopy(self._records[key]) for key in removed[:MAX_PREVIEW]
            ],
            "preview_truncated": len(removed) > MAX_PREVIEW,
            "focus": {
                "before": self._summary(slices.items[()].envelopes.baseline, focus, full=True),
                "after": self._summary(self._slice_state(conditional, residual), focus, full=True),
            },
        }

    def _rectangle(self, slices, focus, top_k, group_budget, edge_budget):
        rows = []
        for group_limit in range(group_budget + 1):
            for edge_limit in range(edge_budget + 1):
                best = missing = None
                covered = 0
                for groups, conditional in slices.items.items():
                    if len(groups) > group_limit:
                        continue
                    covered += 1 + (len(conditional.remaining) if edge_limit else 0)
                    bound = self._bound(conditional.envelopes, focus, edge_limit)
                    if bound.rank is not None:
                        proposal = (
                            -bound.rank,
                            len(groups) + len(bound.rank_edges),
                            groups,
                            bound.rank_edges,
                        )
                        if best is None or proposal < best:
                            best = proposal
                    if bound.unsupported_edges is not None:
                        proposal = (
                            len(groups) + len(bound.unsupported_edges),
                            groups,
                            bound.unsupported_edges,
                        )
                        if missing is None or proposal < missing:
                            missing = proposal
                rank = -best[0] if best else None
                rows.append(
                    {
                        "group_budget": group_limit,
                        "edge_budget": edge_limit,
                        "worst_supported_rank": rank,
                        "unsupported_attainable": missing is not None,
                        "robust": missing is None and rank is not None and rank <= top_k,
                        "covered_action_representations": covered,
                        "rank_witness": self._mixed_witness(
                            slices, focus, best[2:] if best else None
                        ),
                        "unsupported_witness": self._mixed_witness(
                            slices, focus, missing[1:] if missing else None
                        ),
                    }
                )
        return rows

    def _mixed_certificate(self, disease, compound, focus, top_k, budgets, kind, groups, slices):
        group_budget, edge_budget = budgets
        rows = self._rectangle(slices, focus, top_k, group_budget, edge_budget)
        result = {
            "schema_version": "1.0",
            "method": METHOD,
            "disease": disease,
            "compound": compound,
            "top_k": top_k,
            "group_budget": group_budget,
            "edge_budget": edge_budget,
            "scope": {
                "relationship": "BINDS",
                "operation": "withdraw_group_then_delete_residual_record",
                "group_kind": kind,
                "group_ids": list(groups),
                "groups": [self._metadata(key) for key in groups],
                "eligible_group_count": len(groups),
                "eligible_edge_count": len(self._records),
                "candidate_count": len(self._compounds),
                "includes_competitor_changes": True,
            },
            "identity": deepcopy(self._identity),
            "baseline": self._summary(slices.items[()].envelopes.baseline, focus, full=True),
            "results": rows,
            "proof": {
                "algorithm": (
                    "conditional batched one-edge envelopes and exact disjoint rank allocation"
                ),
                "search_group_budget": 1,
                "search_edge_budget": 1,
                "local_states_evaluated": slices.local_states,
                "conditional_slice_count": len(slices.items),
                "envelope_table_sha256": slices.digest,
                "conditional_slices": [
                    {
                        "group_ids": list(keys),
                        "remaining_edge_count": len(value.remaining),
                        "local_states_evaluated": value.envelopes.local_states,
                        "bounds_sha256": value.envelopes.bounds_sha256,
                    }
                    for keys, value in slices.items.items()
                ],
                "covered_action_representations": rows[-1]["covered_action_representations"],
                "count_semantics": (
                    "Action representations may produce identical removed unions; counts are "
                    "not unique edited graphs or measured speedups. All selected 1+1 slices "
                    "are cached even when the requested rectangle is smaller."
                ),
            },
            "interpretation": INTERPRETATION,
        }
        result["certificate_sha256"] = certificate_digest(result)
        return result

    def audit(
        self,
        disease_id,
        compound_id,
        top_k=10,
        group_budget=1,
        edge_budget=1,
        group_kind="source",
        group_ids=None,
    ):
        """Certify every cell in the requested rectangular mixed-action budget."""
        self._limits(top_k, group_budget, edge_budget)
        disease, compound, focus = self._resolve(disease_id, compound_id)
        groups = self._selection(group_kind, group_ids)
        return self._mixed_certificate(
            disease,
            compound,
            focus,
            top_k,
            (group_budget, edge_budget),
            group_kind,
            groups,
            self._slices(disease_id, groups),
        )

    def baseline_candidates(self, disease_id, limit=10):
        """Share the default source-scope construction across every baseline focus."""
        self._limits(limit, 0, 0)
        disease = self._inputs.nodes.get(disease_id)
        if disease is None or disease["label"] != "Disease":
            raise KeyError(f"Unknown disease: {disease_id}")
        baseline = (
            self._slices(disease_id, self._selection("source", None)).items[()].envelopes.baseline
        )
        ordered = sorted(np.flatnonzero(baseline.ranks), key=lambda index: baseline.ranks[index])
        return [
            {
                "id": self._compounds[index],
                "name": self._inputs.nodes[self._compounds[index]]["name"],
                **self._summary(baseline, index, full=True),
            }
            for index in ordered[:limit]
        ]

    def replay(self, disease_id, compound_id, group_ids=(), removed_edge_ids=()):
        """Rebuild the complete edited sparse graph independently of envelopes."""
        _, _, focus = self._resolve(disease_id, compound_id)
        for name, values, allowed in (
            ("group", group_ids, self._groups),
            ("residual edge", removed_edge_ids, self._records),
        ):
            if (
                not isinstance(values, (list, tuple))
                or len(values) > 1
                or any(not isinstance(value, str) or value not in allowed for value in values)
            ):
                raise ValueError(f"Replay requires at most one known {name} ID")
        grouped = self._groups[group_ids[0]] if group_ids else ()
        if set(grouped).intersection(removed_edge_ids):
            raise ValueError("Residual edge must survive the group withdrawal")
        removed = tuple(sorted((*grouped, *removed_edge_ids)))
        state = self._matrix_replay(disease_id, removed)
        return {
            "disease_id": disease_id,
            "compound_id": compound_id,
            "group_ids": list(group_ids),
            "residual_edge_ids": list(removed_edge_ids),
            "removed_edge_count": len(removed),
            "removed_edge_ids_sha256": _digest(removed),
            "focus": self._summary(state, focus, full=True),
            "supported_candidates": int(np.count_nonzero(state.ranks)),
            "verification_method": "edited CSR matrices and full sparse path products",
        }

    def verify(self, certificate):
        """Recompute every bound and independently replay all distinct witnesses."""
        checks, errors, replayed = [], [], 0
        try:
            if not isinstance(certificate, dict):
                raise ValueError("Certificate must be a JSON object")
            if len(json.dumps(certificate, allow_nan=False).encode()) > MAX_CERTIFICATE_BYTES:
                raise ValueError("Mixed certificate exceeds 256 KiB")
            if certificate.get("method") != METHOD or certificate.get("schema_version") != "1.0":
                raise ValueError("Unsupported mixed method or schema")
            if certificate.get("identity") != self._identity:
                raise ValueError("Mixed certificate identity or scorer does not match")
            if certificate.get("certificate_sha256") != certificate_digest(certificate):
                raise ValueError("Certificate checksum does not match its contents")
            checks.append("Certificate identity and content checksum match")
            top_k = certificate["top_k"]
            budgets = certificate["group_budget"], certificate["edge_budget"]
            self._limits(top_k, *budgets)
            disease_id, compound_id = certificate["disease"]["id"], certificate["compound"]["id"]
            disease, compound, focus = self._resolve(disease_id, compound_id)
            kind, selected = certificate["scope"]["group_kind"], certificate["scope"]["group_ids"]
            groups = self._selection(kind, selected if selected else None)
            expected = self._mixed_certificate(
                disease,
                compound,
                focus,
                top_k,
                budgets,
                kind,
                groups,
                self._slices(disease_id, groups, verification=True),
            )
            if _digest(expected) != _digest(certificate):
                raise ValueError("Certificate fields disagree with recomputed exact mixed bounds")
            checks.append("All fields match independently reconstructed conditional envelopes")
            seen = set()
            for row in certificate["results"]:
                for name in ("rank_witness", "unsupported_witness"):
                    witness = row[name]
                    if witness is None:
                        continue
                    key = tuple(witness["group_ids"]), tuple(witness["residual_edge_ids"])
                    if key in seen:
                        continue
                    actual = self.replay(disease_id, compound_id, *key)
                    if (
                        actual["focus"] != witness["focus"]["after"]
                        or actual["removed_edge_count"] != witness["removed_edge_count"]
                        or actual["removed_edge_ids_sha256"] != witness["removed_edge_ids_sha256"]
                    ):
                        raise ValueError("Independent full-matrix mixed witness replay disagrees")
                    seen.add(key)
            replayed = len(seen)
            checks.append("Every distinct witness matches independent full-matrix replay")
        except (KeyError, TypeError, ValueError, RuntimeError, OverflowError, IndexError) as error:
            errors.append(str(error))
        return {
            "status": "invalid" if errors else "verified",
            "valid": not errors,
            "checks": checks,
            "errors": errors,
            "replayed_witnesses": replayed,
            "verification_method": (
                "Separate same-algorithm conditional-envelope recomputation and independent "
                "edited-matrix replay. Exhaustive tiny-graph maximality is tested separately."
            ),
        }

    def _attack_key(self, state, focus, top_k):
        objective = int(state.ranks[focus]) or len(self._compounds) + 1
        rivals = sorted(
            (int(index) for index in np.flatnonzero(state.ranks) if index != focus),
            key=lambda index: state.ranks[index],
        )
        threshold = state.scores[rivals[top_k - 1]] if len(rivals) >= top_k else -np.inf
        return -objective, float(state.scores[focus] - threshold), float(state.scores[focus])

    def _greedy_edge(self, conditional, focus, top_k):
        state = conditional.envelopes.baseline
        if not conditional.remaining:
            return ()
        ranks = (
            self._next_ranks(
                state, focus, conditional.owners, conditional.scores, conditional.supported
            )
            if state.ranks[focus]
            else np.full(len(conditional.remaining), len(self._compounds) + 1, dtype=np.int64)
        )
        margins, focal_scores = self._next_margins(
            state, focus, conditional.owners, conditional.scores, conditional.supported, top_k
        )
        # Include no action, with first tie priority; retain the best feasible prefix.
        base = self._attack_key(state, focus, top_k)
        chosen = int(
            np.lexsort(
                (
                    np.arange(len(ranks) + 1),
                    np.r_[base[2], focal_scores],
                    np.r_[base[1], margins],
                    np.r_[base[0], -ranks],
                )
            )[0]
        )
        return () if chosen == 0 else (conditional.remaining[chosen - 1],)

    def greedy(self, disease_id, compound_id, top_k=10, group_kind="source", group_ids=None):
        """Strong two-order greedy baseline in the identical 1+1 threat space."""
        self._limits(top_k, 1, 1)
        _, _, focus = self._resolve(disease_id, compound_id)
        groups = self._selection(group_kind, group_ids)
        slices = self._slices(disease_id, groups)
        first_group = min(
            slices.items,
            key=lambda selected: (
                self._attack_key(slices.items[selected].envelopes.baseline, focus, top_k),
                len(selected),
                selected,
            ),
        )
        first_slice = slices.items[first_group]
        source_first = first_group, self._greedy_edge(first_slice, focus, top_k)
        first_edge = self._greedy_edge(slices.items[()], focus, top_k)
        choices = [
            (selected, () if set(first_edge).intersection(value.removed) else first_edge)
            for selected, value in slices.items.items()
        ]

        def choice_key(choice):
            selected, residual = choice
            return (
                self._attack_key(self._slice_state(slices.items[selected], residual), focus, top_k),
                len(selected) + len(residual),
                selected,
                residual,
            )

        edge_first = min(choices, key=choice_key)
        strongest = min((source_first, edge_first), key=choice_key)
        result = {
            "method": (
                "Two-order global-rank greedy: source-first and edge-first; the first "
                "action is chosen without lookahead, then the other action is optimized. "
                "Unsupported beats supported; ties minimize focus-score minus kth "
                "supported-rival score, then focus-score, action count and IDs. No-action "
                "prefixes are included. A first edge swallowed by a group is deduplicated."
            ),
            "guarantee": "Attainable witnesses only; no optimality or robustness guarantee",
        }
        for name, choice in (
            ("source_first", source_first),
            ("edge_first", edge_first),
            ("strongest", strongest),
        ):
            witness = self._mixed_witness(slices, focus, choice)
            final = witness["focus"]["after"]
            result[name] = {
                "group_ids": witness["group_ids"],
                "residual_edge_ids": witness["residual_edge_ids"],
                "focus": final,
                "failure_found": not final["supported"] or final["rank"] > top_k,
            }
        return result
