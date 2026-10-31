"""Exact typed-path analysis and reproducible inference over the Hetionet slice.

The graph contains evidence relationships only. Treatment labels are read into a
separate lookup and never participate in matrix products or graph algorithms.
"""

from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import time

import numpy as np
from scipy import sparse

# SciPy exposes this compiled ufunc dynamically; pylint cannot inspect it.
from scipy.special import expit  # pylint: disable=no-name-in-module

FAMILIES = frozenset({"BINDS", "ASSOCIATES", "INTERACTS", "PARTICIPATES"})
FEATURE_NAMES = [
    "log_direct",
    "log_interaction",
    "log_pathway",
    "normalized_direct",
    "normalized_interaction",
    "normalized_pathway",
    "log_compound_degree",
    "log_disease_degree",
]
FEATURE_DETAILS = (
    ("Direct paths", "direct", "log1p(direct_path_count)"),
    ("Interaction paths", "interaction", "log1p(interaction_path_count)"),
    ("Shared-pathway paths", "pathway", "log1p(pathway_path_count)"),
    ("Normalized direct paths", "direct", "log1p(direct_path_count / degree_divisor)"),
    (
        "Normalized interaction paths",
        "interaction",
        "log1p(interaction_path_count / degree_divisor)",
    ),
    ("Normalized pathway paths", "pathway", "log1p(pathway_path_count / degree_divisor)"),
    ("Compound binding degree", "compound_degree", "log1p(compound_binding_degree)"),
    ("Disease association degree", "disease_degree", "log1p(disease_association_degree)"),
)
DISCLAIMER = (
    "Research hypotheses from a historical knowledge graph. Rankings are not "
    "validated treatments, clinical recommendations, or probabilities of efficacy."
)


def validate_exclusions(exclude=()) -> tuple[str, ...]:
    """Reject unknown edge families instead of silently ignoring a request."""
    if isinstance(exclude, str):
        exclude = [value for value in exclude.split(",") if value]
    result = tuple(sorted(set(exclude)))
    if not set(result) <= FAMILIES:
        raise ValueError("Unknown evidence family: " + ", ".join(set(result) - FAMILIES))
    return result


def _read_json(path: Path, default=None):
    """Read an artifact if present, retaining an explicit untrained state otherwise."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _masked_counts(values: np.ndarray, excluded: tuple[str, ...]) -> np.ndarray:
    """Apply one exclusion definition to a complete tensor, disease or single pair."""
    counts = values.copy()
    if "BINDS" in excluded or "ASSOCIATES" in excluded:
        counts[:] = 0
    if "INTERACTS" in excluded:
        counts[..., 1] = 0
    if "PARTICIPATES" in excluded:
        counts[..., 2] = 0
    return counts


def _transform_features(counts, compound_degree, disease_degree) -> np.ndarray:
    """Share the exact training feature transformations with scalar explanations."""
    counts = np.asarray(counts, dtype=float)
    compound_degree, disease_degree = np.broadcast_arrays(
        np.asarray(compound_degree, dtype=float), np.asarray(disease_degree, dtype=float)
    )
    divisor = np.sqrt(np.maximum(compound_degree * disease_degree, 1))
    return np.concatenate(
        [
            np.log1p(counts),
            np.log1p(counts / divisor[..., None]),
            np.log1p(compound_degree)[..., None],
            np.log1p(disease_degree)[..., None],
        ],
        axis=-1,
    )


class GraphEngine:
    """Read-only graph inference shared by the API, benchmark and static export."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        graph = _read_json(self.data_dir / "graph.json")
        if graph is None:
            raise FileNotFoundError("graph.json is missing; run python -m scripts.prepare_data")
        self.manifest = _read_json(self.data_dir / "manifest.json", graph.get("metadata", {}))
        self.nodes = {node["id"]: node for node in graph["nodes"]}
        self.edges = {edge["id"]: edge for edge in graph["edges"]}
        self.entities = {
            label: sorted(node["id"] for node in graph["nodes"] if node["label"] == label)
            for label in ("Compound", "Gene", "Disease", "Pathway")
        }
        self.positions = {
            label: {identifier: index for index, identifier in enumerate(identifiers)}
            for label, identifiers in self.entities.items()
        }
        self.known_treatments = {
            (edge["source"], edge["target"]) for edge in graph.get("treatments", [])
        }
        self.edge_lookup = self._index_edges()
        self.matrices = self._build_matrices()
        self.endpoint_degrees = {
            "Compound": np.asarray(self.matrices["BINDS"].sum(axis=1)).ravel().astype(float),
            "Disease": np.asarray(self.matrices["ASSOCIATES"].sum(axis=1)).ravel().astype(float),
        }
        self.path_counts = self._compute_path_counts()
        self.model = _read_json(self.data_dir / "model.json")
        self.report = _read_json(self.data_dir / "evaluation.json")
        self._verify_artifacts()

    def _verify_artifacts(self) -> None:
        """Detect corrupt or mismatched graph/model artifacts before serving scores."""
        expected = self.manifest.get("graph_sha256")
        if expected:
            with (self.data_dir / "graph.json").open("rb") as source:
                actual = hashlib.file_digest(source, "sha256").hexdigest()
            if actual != expected:
                raise ValueError("Processed graph checksum mismatch; regenerate the dataset")
        if self.model is None:
            return
        if self.model.get(
            "dataset_sha256", self.manifest.get("dataset_sha256")
        ) != self.manifest.get("dataset_sha256"):
            raise ValueError("Model and graph refer to different dataset versions")
        if self.model.get("feature_names", FEATURE_NAMES) != FEATURE_NAMES:
            raise ValueError("Model feature definitions do not match this engine")
        if "model_sha256" in self.model:
            unsigned = {key: value for key, value in self.model.items() if key != "model_sha256"}
            actual = hashlib.sha256(json.dumps(unsigned, sort_keys=True).encode()).hexdigest()
            if actual != self.model["model_sha256"]:
                raise ValueError("Model checksum mismatch; rerun the experiment")

    def _index_edges(self) -> dict:
        """Index typed evidence edges, exposing both orientations for interactions."""
        lookup = {}
        for edge in self.edges.values():
            relation = edge["type"]
            if relation not in FAMILIES:
                raise ValueError(f"Label leakage or unsupported evidence relation: {relation}")
            lookup[(edge["source"], edge["target"], relation)] = edge["id"]
            if relation == "INTERACTS":
                lookup[(edge["target"], edge["source"], relation)] = edge["id"]
        return lookup

    def _build_matrices(self) -> dict[str, sparse.csr_matrix]:
        """Create binary type-specific adjacencies; labels are never consulted."""
        specs = {
            "BINDS": ("Compound", "Gene"),
            "ASSOCIATES": ("Disease", "Gene"),
            "INTERACTS": ("Gene", "Gene"),
            "PARTICIPATES": ("Gene", "Pathway"),
        }
        coordinates = defaultdict(lambda: ([], []))
        for edge in self.edges.values():
            relation = edge["type"]
            left, right = specs[relation]
            row = self.positions[left][edge["source"]]
            column = self.positions[right][edge["target"]]
            if relation == "INTERACTS" and row == column:
                raise ValueError("Self-interaction edges violate the simple-path contract")
            coordinates[relation][0].append(row)
            coordinates[relation][1].append(column)
            if relation == "INTERACTS":
                coordinates[relation][0].append(column)
                coordinates[relation][1].append(row)
        matrices = {}
        for relation, (left, right) in specs.items():
            rows, columns = coordinates[relation]
            matrix = sparse.csr_matrix(
                (np.ones(len(rows), dtype=np.int64), (rows, columns)),
                shape=(len(self.entities[left]), len(self.entities[right])),
                dtype=np.int64,
            )
            matrix.sum_duplicates()
            if matrix.nnz:
                matrix.data[:] = 1
            matrices[relation] = matrix
        return matrices

    def _compute_path_counts(self) -> np.ndarray:
        """Count all three simple metapaths without materializing a gene clique."""
        bindings = self.matrices["BINDS"]
        associations = self.matrices["ASSOCIATES"]
        interactions = self.matrices["INTERACTS"]
        pathways = self.matrices["PARTICIPATES"]
        direct = (bindings @ associations.T).toarray()
        interaction = ((bindings @ interactions) @ associations.T).toarray()
        pathway = ((bindings @ pathways) @ (associations @ pathways).T).toarray()
        # C-G-P-G-D with the same gene twice is a walk, not a simple path.
        repeated_gene = (
            bindings.multiply(np.asarray(pathways.sum(axis=1)).ravel()) @ associations.T
        ).toarray()
        pathway -= repeated_gene
        if np.any(pathway < 0):
            raise ValueError("Pathway counting invariant failed")
        return np.stack([direct, interaction, pathway], axis=-1).astype(np.int64)

    def _entity(self, identifier: str, label: str) -> dict:
        """Resolve a typed ID and fail clearly for absent or wrong-type entities."""
        node = self.nodes.get(identifier)
        if node is None or node["label"] != label:
            raise KeyError(f"Unknown {label.lower()}: {identifier}")
        return {"id": identifier, "name": node["name"]}

    def counts(self, exclude=()) -> np.ndarray:
        """Return exact full path counts after removing whole relationship families."""
        return _masked_counts(self.path_counts, validate_exclusions(exclude))

    def feature_matrix(self, exclude=()) -> np.ndarray:
        """Compute fixed feature definitions with ablated degrees recomputed exactly."""
        excluded = validate_exclusions(exclude)
        compound_degree = self.endpoint_degrees["Compound"] * ("BINDS" not in excluded)
        disease_degree = self.endpoint_degrees["Disease"] * ("ASSOCIATES" not in excluded)
        return _transform_features(
            self.counts(excluded), compound_degree[:, None], disease_degree[None, :]
        )

    def _linear_prediction(self, values: np.ndarray) -> np.ndarray:
        """Apply the unchanged scaler and linear model to either scalar or bulk features."""
        if self.model is None:
            raise RuntimeError("model.json is missing; run python -m scripts.evaluate")
        standardized = (values - np.asarray(self.model["mean"])) / np.asarray(self.model["scale"])
        return standardized @ np.asarray(self.model["coefficients"]) + self.model["intercept"]

    @lru_cache(maxsize=16)
    def _scores(self, excluded: tuple[str, ...]) -> np.ndarray:
        """Apply the saved scaler and coefficients, unchanged for every ablation."""
        return expit(self._linear_prediction(self.feature_matrix(excluded)))

    def stats(self) -> dict:
        """Return verifiable graph size and model identity."""
        return {
            **self.manifest,
            "diseases": len(self.entities["Disease"]),
            "compounds": len(self.entities["Compound"]),
            "model": self.model["name"] if self.model else "untrained",
            "disclaimer": DISCLAIMER,
        }

    def score_matrix(self, exclude=()) -> np.ndarray:
        """Return model scores for every compound–disease pair, including unsupported ones."""
        return self._scores(validate_exclusions(exclude)).copy()

    def diseases(self, query: str = "", limit: int = 30, offset: int = 0) -> dict:
        """Search disease names or IDs with bounded stable pagination."""
        if limit < 1 or limit > 137 or offset < 0:
            raise ValueError("Invalid disease pagination")
        query = query.casefold().strip()
        items = [
            self._entity(identifier, "Disease")
            for identifier in self.entities["Disease"]
            if query in self.nodes[identifier]["name"].casefold() or query in identifier.casefold()
        ]
        items.sort(key=lambda item: (item["name"].casefold(), item["id"]))
        return {"items": items[offset : offset + limit], "total": len(items)}

    @lru_cache(maxsize=128)
    def _rank_positions(self, disease_index: int, excluded: tuple[str, ...]) -> np.ndarray:
        """Cache full supported ranks; zero denotes an unsupported compound, not a tie."""
        counts = _masked_counts(self.path_counts[:, disease_index], excluded)
        scores = self._scores(excluded)[:, disease_index]
        order = sorted(
            np.where(counts.sum(axis=1) > 0)[0],
            key=lambda index: (-scores[index], self.entities["Compound"][index]),
        )
        ranks = np.zeros(len(self.entities["Compound"]), dtype=np.int64)
        ranks[order] = np.arange(1, len(order) + 1)
        return ranks

    def _ranking_rows(self, disease_id: str, excluded: tuple[str, ...]) -> list[dict]:
        """Rank supported compounds and retain deterministic baseline rank positions."""
        disease_index = self.positions["Disease"][disease_id]
        counts = _masked_counts(self.path_counts[:, disease_index], excluded)
        scores = self._scores(excluded)[:, disease_index]
        baseline_ranks = self._rank_positions(disease_index, ())
        current_ranks = self._rank_positions(disease_index, excluded)
        order = sorted(np.flatnonzero(current_ranks), key=lambda index: current_ranks[index])
        rows = []
        for rank, index in enumerate(order, start=1):
            identifier = self.entities["Compound"][index]
            features = dict(zip(("direct", "interaction", "pathway"), map(int, counts[index])))
            rows.append(
                {
                    **self._entity(identifier, "Compound"),
                    "rank": rank,
                    "score": round(float(scores[index]), 8),
                    "baseline_rank": int(baseline_ranks[index]),
                    "rank_delta": int(baseline_ranks[index]) - rank,
                    "known_treatment": (identifier, disease_id) in self.known_treatments,
                    "features": features,
                    "evidence_count": int(counts[index].sum()),
                }
            )
        return rows

    def _assessment_state(self, compound_index: int, disease_index: int, excluded: tuple):
        """Resolve one pair without building another full compound-by-disease tensor."""
        counts = _masked_counts(self.path_counts[compound_index, disease_index], excluded)
        values = _transform_features(
            counts,
            self.endpoint_degrees["Compound"][compound_index] * ("BINDS" not in excluded),
            self.endpoint_degrees["Disease"][disease_index] * ("ASSOCIATES" not in excluded),
        )
        logit = float(self._linear_prediction(values))
        rank = int(self._rank_positions(disease_index, excluded)[compound_index]) or None
        return {
            "supported": rank is not None,
            "rank": rank,
            "score": float(self._scores(excluded)[compound_index, disease_index]),
            "score_status": "supported_retrieval" if rank is not None else "unsupported_diagnostic",
            "logit": logit,
            "evidence_count": int(counts.sum()),
            "features": dict(zip(("direct", "interaction", "pathway"), map(int, counts))),
        }, values

    def _decomposition(self, before: np.ndarray, after: np.ndarray) -> dict:
        """Explain additive logit terms relative to the saved training-feature means."""
        means = np.asarray(self.model["mean"])
        scales = np.asarray(self.model["scale"])
        coefficients = np.asarray(self.model["coefficients"])
        before_scaled, after_scaled = (before - means) / scales, (after - means) / scales
        before_terms, after_terms = coefficients * before_scaled, coefficients * after_scaled
        return {
            "reference": "training_mean",
            "units": "logit",
            "intercept": float(self.model["intercept"]),
            "degree_divisor": "sqrt(max(compound_binding_degree * disease_association_degree, 1))",
            "features": [
                {
                    "name": name,
                    "label": FEATURE_DETAILS[index][0],
                    "group": FEATURE_DETAILS[index][1],
                    "definition": FEATURE_DETAILS[index][2],
                    "value_before": float(before[index]),
                    "value_after": float(after[index]),
                    "mean": float(means[index]),
                    "scale": float(scales[index]),
                    "coefficient": float(coefficients[index]),
                    "standardized_before": float(before_scaled[index]),
                    "standardized_after": float(after_scaled[index]),
                    "contribution_before": float(before_terms[index]),
                    "contribution_after": float(after_terms[index]),
                    "contribution_delta": float(after_terms[index] - before_terms[index]),
                }
                for index, name in enumerate(FEATURE_NAMES)
            ],
        }

    def assessment(self, disease_id: str, compound_id: str, exclude=()) -> dict:
        """Explain any valid pair, preserving diagnostic scores when evidence disappears."""
        disease = self._entity(disease_id, "Disease")
        compound = self._entity(compound_id, "Compound")
        excluded = validate_exclusions(exclude)
        compound_index = self.positions["Compound"][compound_id]
        disease_index = self.positions["Disease"][disease_id]
        baseline, before_values = self._assessment_state(compound_index, disease_index, ())
        current, after_values = self._assessment_state(compound_index, disease_index, excluded)
        return {
            "schema_version": "1.0",
            "disease": disease,
            "compound": compound,
            "known_treatment": (compound_id, disease_id) in self.known_treatments,
            "excluded": list(excluded),
            "model": {
                "name": self.model["name"],
                "version": self.model.get("version"),
                "model_sha256": self.model.get("model_sha256")
                or hashlib.sha256(json.dumps(self.model, sort_keys=True).encode()).hexdigest(),
                "dataset_sha256": self.manifest.get("dataset_sha256"),
            },
            "baseline": baseline,
            "current": current,
            "delta": {
                "score": current["score"] - baseline["score"],
                "logit": current["logit"] - baseline["logit"],
                "rank": (
                    baseline["rank"] - current["rank"]
                    if baseline["supported"] and current["supported"]
                    else None
                ),
                "evidence_count": current["evidence_count"] - baseline["evidence_count"],
            },
            "decomposition": self._decomposition(before_values, after_values),
            "interpretation": (
                "The all-evidence baseline and selected scenario use the same fitted model. "
                "The intercept plus signed contributions equals the logit; applying the "
                "sigmoid gives the retrieval score, within floating-point precision. "
                "Contributions are relative to the training-feature means, so an absent "
                "feature can have a nonzero contribution. Contribution changes add in logit "
                "space, not score or probability space. A score without supporting paths is "
                "diagnostic only and has no supported rank. This is model sensitivity, not "
                "causal biological evidence or a probability of clinical efficacy."
            ),
        }

    def rankings(self, disease_id: str, exclude=(), limit: int = 20, offset: int = 0) -> dict:
        """Return graph-supported hypotheses with exact feature counts."""
        started = time.perf_counter()
        disease = self._entity(disease_id, "Disease")
        excluded = validate_exclusions(exclude)
        if limit < 1 or limit > 1552 or offset < 0:
            raise ValueError("Invalid ranking pagination")
        rows = self._ranking_rows(disease_id, excluded)
        return {
            "disease": disease,
            "candidates": rows[offset : offset + limit],
            "total": len(rows),
            "excluded": list(excluded),
            "model": self.model["name"],
            "interpretation": (
                "Relative retrieval score from sampled-unobserved training, not clinical "
                "probability. Known indications are flagged for context and were excluded "
                "from graph features. The production model uses only the training split."
            ),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def _path_iterators(self, disease_id: str, compound_id: str, excluded: tuple[str, ...]):
        """Yield complete simple paths by family in deterministic gene order."""
        compound_index = self.positions["Compound"][compound_id]
        disease_index = self.positions["Disease"][disease_id]
        bound = self.matrices["BINDS"].getrow(compound_index).indices
        associated = set(self.matrices["ASSOCIATES"].getrow(disease_index).indices)
        genes = self.entities["Gene"]
        pathways = self.entities["Pathway"]
        participation = self.matrices["PARTICIPATES"]
        pathway_genes = participation.T.tocsr()
        if "BINDS" in excluded or "ASSOCIATES" in excluded:
            return [iter(()), iter(()), iter(())]

        def direct_paths():
            for gene in bound:
                if gene in associated:
                    yield [compound_id, genes[gene], disease_id], ["BINDS", "ASSOCIATES"], "C-G-D"

        def interaction_paths():
            if "INTERACTS" in excluded:
                return
            for gene in bound:
                for neighbor in self.matrices["INTERACTS"].getrow(gene).indices:
                    if neighbor in associated:
                        yield [compound_id, genes[gene], genes[neighbor], disease_id], [
                            "BINDS",
                            "INTERACTS",
                            "ASSOCIATES",
                        ], "C-G-G-D"

        def pathway_paths():
            if "PARTICIPATES" in excluded:
                return
            for gene in bound:
                for pathway in participation.getrow(gene).indices:
                    for neighbor in pathway_genes.getrow(pathway).indices:
                        if neighbor != gene and neighbor in associated:
                            yield [
                                compound_id,
                                genes[gene],
                                pathways[pathway],
                                genes[neighbor],
                                disease_id,
                            ], ["BINDS", "PARTICIPATES", "PARTICIPATES", "ASSOCIATES"], "C-G-P-G-D"

        return [direct_paths(), interaction_paths(), pathway_paths()]

    def _path(self, node_ids: list[str], relations: list[str], metapath: str) -> dict:
        """Attach exact graph edge identities to a path, preserving stored direction."""
        edge_ids = []
        for source, target, relation in zip(node_ids, node_ids[1:], relations):
            edge_id = self.edge_lookup.get((source, target, relation))
            if edge_id is None:
                edge_id = self.edge_lookup[(target, source, relation)]
            edge_ids.append(edge_id)
        digest = hashlib.sha256("|".join(node_ids).encode()).hexdigest()[:16]
        return {
            "id": "p_" + digest,
            "node_ids": node_ids,
            "edge_ids": edge_ids,
            "metapath": metapath,
            "weight": 1.0,
        }

    def evidence(self, disease_id: str, compound_id: str, exclude=(), limit: int = 12) -> dict:
        """Return bounded representative paths plus exact untruncated metapath counts."""
        disease = self._entity(disease_id, "Disease")
        compound = self._entity(compound_id, "Compound")
        excluded = validate_exclusions(exclude)
        if limit < 1 or limit > 100:
            raise ValueError("Evidence limit must be between 1 and 100")
        counts = self.counts(excluded)[
            self.positions["Compound"][compound_id], self.positions["Disease"][disease_id]
        ]
        iterators = self._path_iterators(disease_id, compound_id, excluded)
        paths = []
        for batch in itertools.zip_longest(*iterators):
            for value in batch:
                if value is not None:
                    paths.append(self._path(*value))
                    if len(paths) == limit:
                        break
            if len(paths) == limit:
                break
        node_ids = {compound_id, disease_id}
        edge_ids = set()
        for path in paths:
            node_ids.update(path["node_ids"])
            edge_ids.update(path["edge_ids"])
        return {
            "disease": disease,
            "compound": compound,
            "nodes": [self.nodes[identifier] for identifier in sorted(node_ids)],
            "edges": [self.edges[identifier] for identifier in sorted(edge_ids)],
            "paths": paths,
            "counts": dict(zip(("direct", "interaction", "pathway"), map(int, counts))),
            "total_paths": int(counts.sum()),
            "truncated": int(counts.sum()) > len(paths),
            "excluded": list(excluded),
            "selection": (
                "Round-robin metapath families; lexicographic entity order within each family"
            ),
        }

    def challenge(self, disease_id: str, exclude, limit: int = 10) -> dict:
        """Compare evidence removal with the original fitted model held fixed."""
        started = time.perf_counter()
        if limit < 1 or limit > 100:
            raise ValueError("Challenge limit must be between 1 and 100")
        disease = self._entity(disease_id, "Disease")
        excluded = validate_exclusions(exclude)
        before = self._ranking_rows(disease_id, ())
        after = self._ranking_rows(disease_id, excluded)
        before_by_id = {row["id"]: row for row in before}
        after_by_id = {row["id"]: row for row in after}
        interesting = list(dict.fromkeys(row["id"] for row in before[:limit] + after[:limit]))
        changes = []
        for identifier in interesting:
            original = before_by_id.get(identifier)
            ablated = after_by_id.get(identifier)
            changes.append(
                {
                    "id": identifier,
                    "name": self.nodes[identifier]["name"],
                    "before_rank": original["rank"] if original else None,
                    "after_rank": ablated["rank"] if ablated else None,
                    "rank_delta": (
                        original["rank"] - ablated["rank"] if original and ablated else None
                    ),
                    "score_before": original["score"] if original else None,
                    "score_after": ablated["score"] if ablated else None,
                }
            )
        return {
            "disease": disease,
            "excluded": list(excluded),
            "before": before[:limit],
            "after": after[:limit],
            "changes": changes,
            "explanation": (
                "Removed relationship families change exact path features while the trained "
                "scaler and coefficients remain fixed. Rank increases can follow competitors "
                "losing evidence. This is evidence sensitivity, not a biological intervention."
            ),
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def similar(self, compound_id: str, limit: int = 10) -> dict:
        """Compute exact Jaccard similarity of compound target neighborhoods."""
        compound = self._entity(compound_id, "Compound")
        if limit < 1 or limit > 100:
            raise ValueError("Similarity limit must be between 1 and 100")
        index = self.positions["Compound"][compound_id]
        bindings = self.matrices["BINDS"]
        intersection = (bindings @ bindings.getrow(index).T).toarray().ravel()
        degrees = np.asarray(bindings.sum(axis=1)).ravel()
        union = degrees + degrees[index] - intersection
        similarity = np.divide(
            intersection, union, out=np.zeros_like(union, dtype=float), where=union > 0
        )
        order = sorted(
            (
                candidate
                for candidate in range(len(similarity))
                if candidate != index and similarity[candidate] > 0
            ),
            key=lambda candidate: (-similarity[candidate], self.entities["Compound"][candidate]),
        )
        return {
            "compound": compound,
            "algorithm": "Compound-target Jaccard similarity",
            "execution_backend": "scipy-exact",
            "items": [
                {
                    **self._entity(self.entities["Compound"][candidate], "Compound"),
                    "similarity": round(float(similarity[candidate]), 8),
                    "shared_targets": int(intersection[candidate]),
                }
                for candidate in order[:limit]
            ],
        }

    def algorithms(self, disease_id: str, limit: int = 10) -> dict:
        """Run personalized PageRank on an undirected evidence-only projection."""
        disease = self._entity(disease_id, "Disease")
        if limit < 1 or limit > 100:
            raise ValueError("Algorithm limit must be between 1 and 100")
        node_ids = sorted(self.nodes)
        positions = {identifier: index for index, identifier in enumerate(node_ids)}
        rows, columns = [], []
        for edge in self.edges.values():
            left, right = positions[edge["source"]], positions[edge["target"]]
            rows.extend((left, right))
            columns.extend((right, left))
        adjacency = sparse.csr_matrix(
            (np.ones(len(rows)), (rows, columns)), shape=(len(node_ids), len(node_ids))
        )
        degrees = np.asarray(adjacency.sum(axis=1)).ravel()
        transition = (
            sparse.diags(np.divide(1.0, degrees, out=np.zeros_like(degrees), where=degrees > 0))
            @ adjacency
        )
        personalization = np.zeros(len(node_ids))
        personalization[positions[disease_id]] = 1.0
        ranks = personalization.copy()
        delta = float("inf")
        iteration = 0
        for iteration in range(1, 501):
            next_ranks = (
                0.85 * (transition.T @ ranks + ranks[degrees == 0].sum() * personalization)
                + 0.15 * personalization
            )
            delta = float(np.abs(next_ranks - ranks).sum())
            ranks = next_ranks
            if delta < 1e-10:
                break
        compounds = sorted(
            self.entities["Compound"],
            key=lambda identifier: (-ranks[positions[identifier]], identifier),
        )
        return {
            "disease": disease,
            "algorithm": "Personalized PageRank",
            "execution_backend": "scipy-power-iteration",
            "damping_factor": 0.85,
            "iterations": iteration,
            "converged": delta < 1e-10,
            "projection": "Undirected evidence relationships only; excludes TREATS and PALLIATES",
            "items": [
                {
                    **self._entity(identifier, "Compound"),
                    "score": float(ranks[positions[identifier]]),
                }
                for identifier in compounds[:limit]
            ],
            "interpretation": "Graph proximity, not probability of treatment efficacy.",
        }

    def evaluation(self) -> dict:
        """Return the executed benchmark, failing if it has not actually run."""
        if self.report is None:
            raise FileNotFoundError("evaluation.json is missing; run python -m scripts.evaluate")
        return self.report

    def provenance(self) -> dict:
        """Expose the dataset identity and granular source attribution policy."""
        return self.manifest
