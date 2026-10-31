"""Coordinate the immutable scientific artifacts and the live graph database."""

from functools import cached_property

from app.binding_audit import BindingAuditor
from app.config import Settings
from app.graph_engine import GraphEngine
from app.neo4j_repository import Neo4jRepository


class EvidenceService:
    """One service boundary shared by API endpoints and LangGraph tools."""

    def __init__(self, settings: Settings, engine=None, repository=None):
        self.settings = settings
        self.engine = engine or GraphEngine(settings.data_dir)
        self.repository = repository
        if settings.graph_backend == "neo4j" and self.repository is None:
            self.repository = Neo4jRepository(settings)
            self.repository.verify(self.engine.manifest.get("dataset_sha256"))

    @cached_property
    def auditor(self):
        """Create the bounded audit engine only when a fitted-model audit is requested."""
        return BindingAuditor(self.engine)

    def evidence(self, disease_id, compound_id, exclude=(), limit=12):
        """Counts use exact sparse algebra, displayed paths use the selected backend."""
        result = self.engine.evidence(disease_id, compound_id, exclude=exclude, limit=limit)
        if self.repository:
            result.update(self.repository.evidence(disease_id, compound_id, exclude, limit))
            result["truncated"] = result["total_paths"] > len(result["paths"])
        else:
            result["execution_backend"] = "memory"
        return result

    def similar(self, compound_id, limit=10, algorithm="cypher"):
        """Validate entity identity even when the database has no shared targets."""
        local = self.engine.similar(compound_id, limit)
        if self.repository:
            result = (
                self.repository.gds_similarity(compound_id, limit)
                if algorithm == "gds"
                else self.repository.similar(compound_id, limit)
            )
            local.update(result)
        return local

    def algorithms(self, disease_id, limit=10):
        """Execute personalized PageRank in GDS when Neo4j is configured."""
        if self.repository:
            self.engine.rankings(disease_id, limit=1)  # Validate the typed identifier.
            return self.repository.algorithms(disease_id, limit)
        return self.engine.algorithms(disease_id, limit)

    def close(self):
        """Release the optional database connection pool."""
        if self.repository:
            self.repository.close()
