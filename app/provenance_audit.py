"""Exact finite correlated provenance-group stress tests and protection plans.

A selected group withdraws every BINDS record mentioning its provider label or
imported PubMed identifier. Overlaps are unions, not independent corroboration.
Unlike single-edge envelopes, a scenario jointly changes every affected rival.
"""

from __future__ import annotations

from collections import OrderedDict, defaultdict
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import itertools
import json
from threading import RLock

import numpy as np

from app.binding_audit import SCORER, canonical_scores, certificate_digest
from app.graph_engine import FEATURE_NAMES

MAX_GROUPS = 16
MAX_BUDGET = 2
MAX_PREVIEW = 12
METHOD = "provenance-group-exhaustive-v1"
INTERPRETATION = (
    "Exact for this fixed model and the selected provenance-group withdrawal space. "
    "Withdrawing a group removes every recorded BINDS edge mentioning that provider "
    "label or imported PubMed identifier, including records with other annotations. "
    "Overlapping groups remove a record once. An annotation is not proof of independent "
    "corroboration, and a PubMed group is not necessarily one experiment. This is a "
    "conservative record-quarantine stress scenario, not a factual retraction, clinical "
    "effect, or probability of error. All competing compounds change jointly. "
    "Protected groups are assumed unavailable for withdrawal; protection does not mean "
    "a review or experiment has established that assumption. Binary64 exactness is "
    "relative to the declared scorer and numerical runtime; verification rejects "
    "numerical mismatches. Other relation families, new records, refitting and "
    "unselected groups are outside scope."
)
PROTECTION_INTERPRETATION = (
    "Minimum cardinality among additional selected groups that must be assumed "
    "unavailable for withdrawal to block every failing scenario in this certificate. "
    "This is a conditional combinatorial protection plan, not an optimal experiment, "
    "a measured review-cost saving, or evidence that the protected records are true. "
    "A record can still be withdrawn through another unprotected overlapping group."
)


def _digest(value):
    """Reuse the documented v1.2 transport-stable JSON numerical convention."""
    return certificate_digest({"value": value})


def _model_parameters(model):
    if model is None:
        raise RuntimeError("A fitted model is required for provenance audits; run evaluate")
    if model.get("feature_names", FEATURE_NAMES) != FEATURE_NAMES:
        raise ValueError("Unsupported provenance model feature definitions")
    if model.get("model_sha256"):
        unsigned = {key: value for key, value in model.items() if key != "model_sha256"}
        actual = hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()
        if actual != model["model_sha256"]:
            raise ValueError("Model checksum changed after the engine was loaded")
    result = {}
    for key in ("mean", "scale", "coefficients"):
        try:
            vector = np.asarray(model[key], dtype=np.float64)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid provenance model {key}") from error
        if vector.shape != (8,) or not np.isfinite(vector).all():
            raise ValueError(f"Invalid provenance model {key}")
        result[key] = vector.copy()
    if np.any(result["scale"] <= 0):
        raise ValueError("Provenance model scales must be positive")
    try:
        intercept = np.asarray(model["intercept"], dtype=np.float64)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Invalid provenance model intercept") from error
    if intercept.shape != () or not np.isfinite(intercept):
        raise ValueError("Invalid provenance model intercept")
    result["intercept"] = np.float64(intercept)
    return result


def _annotation_ids(edge):
    """Preserve provider labels and imported numeric PubMed identifiers exactly."""
    data = edge.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Invalid binding provenance data")
    annotations = {"source": edge.get("sources", []), "pubmed": data.get("pubmed_ids", [])}
    groups = []
    for kind, labels in annotations.items():
        if not isinstance(labels, list) or any(
            not isinstance(label, str) or not label.strip() for label in labels
        ):
            raise ValueError(f"Invalid {kind} provenance annotations")
        for label in labels:
            if kind == "pubmed" and (not label.isascii() or not label.isdecimal()):
                raise ValueError("PubMed identifiers must be nonempty ASCII digits")
            groups.append(f"{kind}:{label}")
    return tuple(groups)


def _rank(scores, counts):
    present = np.flatnonzero(counts.sum(axis=1) > 0)
    ordered = present[np.lexsort((present, -scores[present]))]
    ranks = np.zeros(len(scores), dtype=np.int64)
    ranks[ordered] = np.arange(1, len(ordered) + 1)
    return ranks


@dataclass(frozen=True)
class _State:
    counts: np.ndarray
    scores: np.ndarray
    logits: np.ndarray
    ranks: np.ndarray


@dataclass(frozen=True)
class _Scenarios:
    states: dict
    digest: str


class ProvenanceAuditor:
    """A bounded, immutable audit; catalog lookup works without a fitted model."""

    def __init__(self, engine, cache_size=4):
        if isinstance(cache_size, bool) or not isinstance(cache_size, int) or cache_size < 1:
            raise ValueError("Provenance cache size must be a positive integer")
        self.engine = engine
        self._lock = RLock()
        self._cache_size = cache_size
        self._caches = {key: OrderedDict() for key in ("scenarios", "verification", "replay")}
        self._model = None if engine.model is None else _model_parameters(engine.model)
        self._legacy_scores = None if engine.model is None else engine.score_matrix().copy()
        self._matrices = {key: value.copy() for key, value in engine.matrices.items()}
        self._compounds = tuple(engine.entities["Compound"])
        self._compound_positions = dict(engine.positions["Compound"])
        self._compound_degrees = np.asarray(self._matrices["BINDS"].sum(axis=1)).ravel()
        self._pathway_degrees = np.asarray(self._matrices["PARTICIPATES"].sum(axis=1)).ravel()
        graph_bytes = (engine.data_dir / "graph.json").read_bytes()
        graph_sha256 = hashlib.sha256(graph_bytes).hexdigest()
        if engine.manifest.get("graph_sha256", graph_sha256) != graph_sha256:
            raise ValueError("Graph checksum changed after the engine was loaded")
        self._records, self._coordinates, self._groups = self._load_groups(json.loads(graph_bytes))
        self._metadata = {
            group_id: self._group_metadata(group_id, members)
            for group_id, members in self._groups.items()
        }
        self._identity = {
            "dataset_sha256": engine.manifest.get("dataset_sha256"),
            "graph_sha256": graph_sha256,
            "model_sha256": (
                engine.model.get("model_sha256")
                or hashlib.sha256(json.dumps(engine.model, sort_keys=True).encode()).hexdigest()
                if engine.model is not None
                else None
            ),
            "scorer": SCORER,
            "group_map_sha256": _digest(self._groups),
        }

    def _load_groups(self, graph):
        """Bind imported annotations to unique, validated binary binding records."""
        node_ids = [node["id"] for node in graph["nodes"]]
        if (
            len(node_ids) != len(set(node_ids))
            or set(node_ids) != self.engine.nodes.keys()
            or any(node != self.engine.nodes.get(node["id"]) for node in graph["nodes"])
        ):
            raise ValueError("Graph node identities changed after the engine was loaded")
        records, coordinates, endpoints, ids = {}, {}, set(), set()
        groups = defaultdict(set)
        for edge in graph["edges"]:
            if edge["id"] in ids:
                raise ValueError("Duplicate graph edge ID prevents provenance certification")
            ids.add(edge["id"])
            if edge != self.engine.edges.get(edge["id"]):
                raise ValueError("Graph records changed after the engine was loaded")
            if edge["type"] != "BINDS":
                continue
            pair = (edge["source"], edge["target"])
            if pair in endpoints:
                raise ValueError("Duplicate BINDS endpoints prevent provenance certification")
            endpoints.add(pair)
            try:
                coordinate = (
                    self._compound_positions[edge["source"]],
                    self.engine.positions["Gene"][edge["target"]],
                )
            except KeyError as error:
                raise ValueError("Invalid typed BINDS endpoints") from error
            if self._matrices["BINDS"][coordinate] != 1:
                raise ValueError("BINDS records do not match the graph matrix")
            records[edge["id"]] = deepcopy(edge)
            coordinates[edge["id"]] = coordinate
            for group_id in _annotation_ids(edge):
                groups[group_id].add(edge["id"])
        if ids != self.engine.edges.keys():
            raise ValueError("Graph records changed after the engine was loaded")
        if len(records) != self._matrices["BINDS"].nnz:
            raise ValueError("BINDS records do not match the binary graph matrix")
        return (
            records,
            coordinates,
            {key: tuple(sorted(value)) for key, value in sorted(groups.items())},
        )

    def _group_metadata(self, group_id, members):
        kind, label = group_id.split(":", 1)
        result = {
            "group_id": group_id,
            "label": label if kind == "source" else f"PubMed {label}",
            "edge_count": len(members),
            "compound_count": len({self._coordinates[edge][0] for edge in members}),
            "edge_ids_sha256": _digest(members),
        }
        if kind == "pubmed":
            result["url"] = f"https://pubmed.ncbi.nlm.nih.gov/{label}/"
        return result

    def catalog(self, kind="source", query="", limit=30, offset=0):
        """List observed BINDS provenance; missing annotations remain explicit."""
        if kind not in ("source", "pubmed"):
            raise ValueError("Group kind must be source or pubmed")
        if not isinstance(query, str):
            raise ValueError("Catalog query must be a string")
        for name, value, minimum, maximum in (
            ("limit", limit, 1, 100),
            ("offset", offset, 0, 100000),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(f"Invalid catalog {name}")
        available = [key for key in self._groups if key.startswith(f"{kind}:")]
        matching = [key for key in available if query.casefold() in key.casefold()]
        annotated = set().union(*(self._groups[key] for key in available)) if available else set()
        return {
            "kind": kind,
            "items": deepcopy([self._metadata[key] for key in matching[offset : offset + limit]]),
            "total": len(matching),
            "offset": offset,
            "limit": limit,
            "identity": {
                key: self._identity[key]
                for key in ("dataset_sha256", "graph_sha256", "group_map_sha256")
            },
            "coverage": {
                "binding_edges": len(self._records),
                "annotated_binding_edges": len(annotated),
                "unannotated_binding_edges": len(self._records) - len(annotated),
            },
            "semantics": INTERPRETATION,
        }

    def _selection(self, group_kind, group_ids, protected_group_ids):
        if group_kind not in ("source", "pubmed"):
            raise ValueError("Group kind must be source or pubmed")
        if group_ids is None:
            if group_kind == "pubmed":
                raise ValueError("PubMed auditing requires an explicit selection of 1..16 groups")
            group_ids = [key for key in self._groups if key.startswith("source:")]
        if not isinstance(group_ids, (list, tuple)) or any(
            not isinstance(key, str) for key in group_ids
        ):
            raise ValueError("Group IDs must be a list of strings")
        if len(set(group_ids)) != len(group_ids) or len(group_ids) > MAX_GROUPS:
            raise ValueError("Select at most 16 distinct provenance groups")
        if group_kind == "pubmed" and not group_ids:
            raise ValueError("PubMed auditing requires an explicit selection of 1..16 groups")
        if any(
            key not in self._groups or not key.startswith(f"{group_kind}:") for key in group_ids
        ):
            raise ValueError("Unknown group ID or group kind mismatch")
        protected_group_ids = [] if protected_group_ids is None else protected_group_ids
        if not isinstance(protected_group_ids, (list, tuple)) or any(
            not isinstance(key, str) for key in protected_group_ids
        ):
            raise ValueError("Protected group IDs must be a list of strings")
        if len(set(protected_group_ids)) != len(protected_group_ids):
            raise ValueError("Protected group IDs must be distinct")
        if not set(protected_group_ids) <= set(group_ids):
            raise ValueError("Protected groups must belong to the selected scope")
        return tuple(sorted(group_ids)), tuple(sorted(protected_group_ids))

    def _resolve(self, disease_id, compound_id, top_k, budget):
        if self._model is None:
            raise RuntimeError("A fitted model is required for provenance audits; run evaluate")
        for key, label in ((disease_id, "Disease"), (compound_id, "Compound")):
            node = self.engine.nodes.get(key)
            if node is None or node["label"] != label:
                raise KeyError(f"Unknown {label.lower()}: {key}")
        for name, value, maximum in (("top_k", top_k, 100), ("budget", budget, MAX_BUDGET)):
            minimum = 1 if name == "top_k" else 0
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(
                    f"Provenance {name} must be an integer from {minimum} through {maximum}"
                )
        return self._compound_positions[compound_id]

    def _removed(self, groups):
        return tuple(sorted(set().union(*(self._groups[key] for key in groups)))) if groups else ()

    def _state(self, counts, degrees, disease_degree):
        scores, logits = canonical_scores(counts, degrees, disease_degree, self._model)
        return _State(counts, scores, logits, _rank(scores, counts))

    def _build(self, disease_id, groups):
        disease_index = self.engine.positions["Disease"][disease_id]
        association = self._matrices["ASSOCIATES"].getrow(disease_index).toarray().ravel()
        pathways = self._matrices["PARTICIPATES"]
        contributions = np.column_stack(
            (
                association,
                self._matrices["INTERACTS"] @ association,
                pathways @ (pathways.T @ association) - self._pathway_degrees * association,
            )
        ).astype(np.int64)
        counts = np.asarray(self._matrices["BINDS"] @ contributions, dtype=np.int64)
        if np.any(contributions < 0) or not np.array_equal(
            counts, self.engine.path_counts[:, disease_index]
        ):
            raise ValueError("Provenance path counts disagree with the original graph")
        states = {}
        for size in range(MAX_BUDGET + 1):
            for selected in itertools.combinations(groups, size):
                current, degrees = counts.copy(), self._compound_degrees.copy()
                removed = self._removed(selected)
                if removed:
                    coordinates = np.asarray([self._coordinates[key] for key in removed])
                    np.add.at(current, coordinates[:, 0], -contributions[coordinates[:, 1]])
                    np.add.at(degrees, coordinates[:, 0], -1)
                if np.any(current < 0) or np.any(degrees < 0):
                    raise ValueError("Overlapping provenance groups produced an invalid union")
                states[selected] = self._state(current, degrees, association.sum())
        table_digest = _digest(
            [
                {"groups": key, "scores": state.scores.tolist(), "ranks": state.ranks.tolist()}
                for key, state in states.items()
            ]
        )
        return _Scenarios(states, table_digest)

    def _scenarios(self, disease_id, groups, verification=False):
        key = (disease_id, groups)
        cache = self._caches["verification" if verification else "scenarios"]
        with self._lock:
            if key not in cache:
                cache[key] = self._build(disease_id, groups)
                while len(cache) > self._cache_size:
                    cache.popitem(last=False)
            cache.move_to_end(key)
            return cache[key]

    @staticmethod
    def _summary(state, focus):
        rank = int(state.ranks[focus])
        counts = state.counts[focus]
        return {
            "supported": bool(rank),
            "rank": rank or None,
            "score": float(state.scores[focus]),
            "logit": float(state.logits[focus]),
            "evidence_count": int(counts.sum()),
            "counts": dict(zip(("direct", "interaction", "pathway"), map(int, counts))),
        }

    def _witness(self, scenarios, focus, groups):
        if groups is None:
            return None
        removed = self._removed(groups)
        return {
            "group_ids": list(groups),
            "removed_edge_count": len(removed),
            "removed_edge_ids_sha256": _digest(removed),
            "affected_compound_count": len({self._coordinates[key][0] for key in removed}),
            "removed_edges_preview": [
                deepcopy(self._records[key]) for key in removed[:MAX_PREVIEW]
            ],
            "preview_truncated": len(removed) > MAX_PREVIEW,
            "focus": {
                "before": self._summary(scenarios.states[()], focus),
                "after": self._summary(scenarios.states[groups], focus),
            },
        }

    @staticmethod
    def _bounds(states, focus, top_k):
        supported = [
            (int(state.ranks[focus]), groups) for groups, state in states if state.ranks[focus]
        ]
        missing = [groups for groups, state in states if not state.ranks[focus]]
        maximum = max((rank for rank, _ in supported), default=None)
        witness = next((groups for rank, groups in supported if rank == maximum), None)
        return (
            {
                "worst_supported_rank": maximum,
                "unsupported_attainable": bool(missing),
                "robust": not missing and maximum is not None and maximum <= top_k,
            },
            witness,
            missing[0] if missing else None,
        )

    @staticmethod
    def _protection(states, focus, top_k, available):
        positions = {key: 1 << index for index, key in enumerate(available)}
        failures = [
            groups
            for groups, state in states
            if not state.ranks[focus] or state.ranks[focus] > top_k
        ]
        result = {
            "status": "optimal",
            "minimum_additional_groups": None,
            "representative": [],
            "optimal_set_count": 0,
            "optimal_sets_preview": [],
            "alternatives_truncated": False,
            "failing_scenario_count": len(failures),
            "interpretation": PROTECTION_INTERPRETATION,
        }
        if () in failures:
            result["status"] = "impossible_baseline"
            return result
        masks = [sum(positions[key] for key in groups) for groups in failures]
        for size in range(len(available) + 1):
            count, preview = 0, []
            for selection in itertools.combinations(available, size):
                mask = sum(positions[key] for key in selection)
                if all(mask & failure for failure in masks):
                    count += 1
                    if len(preview) < MAX_PREVIEW:
                        preview.append(list(selection))
            if count:
                result.update(
                    status="already_robust" if size == 0 else "optimal",
                    minimum_additional_groups=size,
                    representative=preview[0],
                    optimal_set_count=count,
                    optimal_sets_preview=preview,
                    alternatives_truncated=count > len(preview),
                )
                return result
        raise ValueError("A finite nonempty failure family must admit protection")

    def _entity(self, identifier):
        return {"id": identifier, "name": self.engine.nodes[identifier]["name"]}

    def _shortlist(self, scenarios, allowed, top_k):
        baseline = scenarios.states[()]
        order = np.argsort(baseline.ranks)
        indices = [int(index) for index in order if 0 < baseline.ranks[index] <= top_k]
        rows = []
        for index in indices[:20]:
            summary, _, _ = self._bounds(allowed, index, top_k)
            rows.append(
                {
                    "compound": self._entity(self._compounds[index]),
                    "baseline_rank": int(baseline.ranks[index]),
                    "baseline_score": float(baseline.scores[index]),
                    **summary,
                }
            )
        return rows, len(indices) > len(rows)

    def _baseline(self, disease_id, focus, scenarios):
        baseline = self._summary(scenarios.states[()], focus)
        disease_index = self.engine.positions["Disease"][disease_id]
        legacy_scores = self._legacy_scores[:, disease_index]
        legacy_ranks = _rank(legacy_scores, scenarios.states[()].counts)
        baseline.update(
            legacy_score=float(legacy_scores[focus]), legacy_rank=int(legacy_ranks[focus]) or None
        )
        return baseline

    def _certificate(
        self, disease_id, compound_id, top_k, budget, kind, groups, protected, scenarios
    ):
        focus = self._compound_positions[compound_id]
        available = tuple(key for key in groups if key not in protected)
        allowed = [
            (keys, state)
            for keys, state in scenarios.states.items()
            if len(keys) <= budget and not set(keys).intersection(protected)
        ]
        baseline = self._baseline(disease_id, focus, scenarios)
        results = []
        for limit in range(budget + 1):
            states = [(keys, state) for keys, state in allowed if len(keys) <= limit]
            summary, rank_witness, missing_witness = self._bounds(states, focus, top_k)
            results.append(
                {
                    "budget": limit,
                    "scenario_count": len(states),
                    **summary,
                    "rank_witness": self._witness(scenarios, focus, rank_witness),
                    "unsupported_witness": self._witness(scenarios, focus, missing_witness),
                }
            )
        shortlist, shortlist_truncated = self._shortlist(scenarios, allowed, top_k)
        result = {
            "schema_version": "1.0",
            "method": METHOD,
            "disease": self._entity(disease_id),
            "compound": self._entity(compound_id),
            "top_k": top_k,
            "budget": budget,
            "scope": {
                "relationship": "BINDS",
                "operation": "withdraw_records_mentioning_any_selected_group",
                "group_kind": kind,
                "group_ids": list(groups),
                "groups": [deepcopy(self._metadata[key]) for key in groups],
                "protected_group_ids": list(protected),
                "eligible_group_count": len(groups),
                "available_group_count": len(available),
                "includes_competitor_changes": True,
            },
            "identity": deepcopy(self._identity),
            "baseline": baseline,
            "results": results,
            "protection_plan": self._protection(allowed, focus, top_k, available),
            "shortlist": shortlist,
            "shortlist_truncated": shortlist_truncated,
            "proof": {
                "algorithm": (
                    "exhaustive bounded group subsets and exact " "minimum-cardinality hitting sets"
                ),
                "search_budget": MAX_BUDGET,
                "scenarios_evaluated": len(scenarios.states),
                "covered_scenarios": len(allowed),
                "scenario_table_sha256": scenarios.digest,
                "group_map_sha256": self._identity["group_map_sha256"],
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
        budget=2,
        group_kind="source",
        group_ids=None,
        protected_group_ids=None,
    ):
        """Certify selected group subsets; conditional protection never edits graph data."""
        self._resolve(disease_id, compound_id, top_k, budget)
        groups, protected = self._selection(group_kind, group_ids, protected_group_ids)
        scenarios = self._scenarios(disease_id, groups)
        return self._certificate(
            disease_id, compound_id, top_k, budget, group_kind, groups, protected, scenarios
        )

    def greedy_protection(
        self,
        disease_id,
        compound_id,
        top_k=10,
        budget=2,
        group_kind="source",
        group_ids=None,
        protected_group_ids=None,
    ):
        """A feasible frequency-greedy baseline with deterministic redundant-set cleanup.

        It observes the same complete failure family as the exact method. Its
        objective is group count, never a measured cost or information value.
        """
        focus = self._resolve(disease_id, compound_id, top_k, budget)
        groups, protected = self._selection(group_kind, group_ids, protected_group_ids)
        scenarios = self._scenarios(disease_id, groups)
        failures = [
            set(keys)
            for keys, state in scenarios.states.items()
            if len(keys) <= budget
            and not set(keys).intersection(protected)
            and (not state.ranks[focus] or state.ranks[focus] > top_k)
        ]
        result = {
            "method": (
                "maximum-uncovered-failure-frequency; group-ID ties; "
                "reverse-ID redundancy cleanup"
            ),
            "guarantee": "Feasible conditional protection only; no minimum-cardinality guarantee",
            "additional_group_count": None,
            "protected_group_ids": [],
            "conditional_robust": False,
        }
        if set() in failures:
            return result
        selected, uncovered = [], failures.copy()
        while uncovered:
            candidates = sorted(set().union(*uncovered))
            chosen = min(
                candidates, key=lambda key: (-sum(key in failure for failure in uncovered), key)
            )
            selected.append(chosen)
            uncovered = [failure for failure in uncovered if chosen not in failure]
        for key in sorted(selected, reverse=True):
            trial = set(selected) - {key}
            if all(trial.intersection(failure) for failure in failures):
                selected.remove(key)
        result.update(
            additional_group_count=len(selected),
            protected_group_ids=sorted(selected),
            conditional_robust=True,
        )
        return result

    def _matrix_replay(self, disease_id, groups):
        key = (disease_id, groups)
        with self._lock:
            if key in self._caches["replay"]:
                self._caches["replay"].move_to_end(key)
                return self._caches["replay"][key]
            bindings = self._matrices["BINDS"].copy().tolil()
            for edge in self._removed(groups):
                bindings[self._coordinates[edge]] = 0
            bindings = bindings.tocsr()
            bindings.eliminate_zeros()
            index = self.engine.positions["Disease"][disease_id]
            association = self._matrices["ASSOCIATES"].getrow(index).T
            pathways = self._matrices["PARTICIPATES"]
            direct = (bindings @ association).toarray().ravel()
            interaction = ((bindings @ self._matrices["INTERACTS"]) @ association).toarray().ravel()
            shared = ((bindings @ pathways) @ (association.T @ pathways).T).toarray().ravel()
            repeated = (bindings.multiply(self._pathway_degrees) @ association).toarray().ravel()
            counts = np.column_stack((direct, interaction, shared - repeated)).astype(np.int64)
            degrees = np.asarray(bindings.sum(axis=1)).ravel()
            state = self._state(counts, degrees, association.sum())
            self._caches["replay"][key] = state
            while len(self._caches["replay"]) > 128:
                self._caches["replay"].popitem(last=False)
            return state

    def replay(self, disease_id, compound_id, group_ids, group_kind="source"):
        """Independently edit CSR matrices and rebuild all surviving simple-path counts."""
        focus = self._resolve(disease_id, compound_id, 10, 2)
        if group_ids in ([], ()):
            if group_kind not in ("source", "pubmed"):
                raise ValueError("Group kind must be source or pubmed")
            groups = ()
        else:
            groups, _ = self._selection(group_kind, group_ids, [])
        if len(groups) > MAX_BUDGET:
            raise ValueError("Replay supports at most two group withdrawals")
        state = self._matrix_replay(disease_id, groups)
        removed = self._removed(groups)
        return {
            "disease_id": disease_id,
            "compound_id": compound_id,
            "group_ids": list(groups),
            "removed_edge_count": len(removed),
            "removed_edge_ids_sha256": _digest(removed),
            "focus": self._summary(state, focus),
            "verification_method": "edited CSR matrices and full sparse path products",
        }

    def verify(self, certificate):
        """Recompute all claims separately and independently replay each distinct witness."""
        checks, errors, replayed = [], [], 0
        try:
            if not isinstance(certificate, dict):
                raise ValueError("Certificate must be a JSON object")
            if certificate.get("certificate_sha256") != certificate_digest(certificate):
                raise ValueError("Certificate checksum does not match its contents")
            checks.append("Certificate content checksum matches")
            if certificate.get("identity") != self._identity:
                raise ValueError("Graph, model, scorer or provenance map identity does not match")
            checks.append("Graph, model, scorer and complete provenance map identities match")
            disease_id, compound_id = certificate["disease"]["id"], certificate["compound"]["id"]
            top_k, budget = certificate["top_k"], certificate["budget"]
            focus = self._resolve(disease_id, compound_id, top_k, budget)
            scope = certificate["scope"]
            groups, protected = self._selection(
                scope["group_kind"], scope["group_ids"], scope["protected_group_ids"]
            )
            scenarios = self._scenarios(disease_id, groups, verification=True)
            expected = self._certificate(
                disease_id,
                compound_id,
                top_k,
                budget,
                scope["group_kind"],
                groups,
                protected,
                scenarios,
            )
            if _digest(certificate) != _digest(expected):
                raise ValueError(
                    "Recomputed bounds, protection optimum or certificate fields do not match"
                )
            checks.append("Every bound, shortlist result and exact protection optimum recomputes")
            seen = set()
            for result in certificate["results"]:
                for key in ("rank_witness", "unsupported_witness"):
                    witness = result[key]
                    if witness is None or tuple(witness["group_ids"]) in seen:
                        continue
                    selected = tuple(witness["group_ids"])
                    seen.add(selected)
                    state = self._matrix_replay(disease_id, selected)
                    if _digest(self._summary(state, focus)) != _digest(witness["focus"]["after"]):
                        raise ValueError("Independent matrix witness replay disagrees")
                    replayed += 1
            checks.append("Every distinct witness independently replays through edited matrices")
        except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as error:
            errors.append(str(error))
        return {
            "status": "invalid" if errors else "verified",
            "valid": not errors,
            "checks": checks,
            "errors": errors,
            "replayed_witnesses": replayed,
            "verification_method": (
                "separate exhaustive recomputation and " "independent full-matrix witness replay"
            ),
        }
