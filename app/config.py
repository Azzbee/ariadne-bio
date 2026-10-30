"""Environment-based application configuration without embedded credentials."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Small immutable configuration boundary, also injectable in tests."""

    data_dir: Path = Path("data/processed")
    graph_backend: str = "memory"
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    agent_mode: str = "auto"
    llm_base_url: str = ""
    llm_model: str = "qwen2.5:1.5b"
    llm_api_key: str = ""
    llm_timeout: float = 60.0
    query_timeout: float = 15.0

    @classmethod
    def from_env(cls) -> "Settings":
        """Read only explicitly supported settings from the environment."""
        return cls(
            data_dir=Path(os.getenv("ARIADNE_DATA_DIR", "data/processed")),
            graph_backend=os.getenv("ARIADNE_GRAPH_BACKEND", "memory"),
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            agent_mode=os.getenv("ARIADNE_AGENT_MODE", "auto"),
            llm_base_url=os.getenv("ARIADNE_LLM_BASE_URL", "").rstrip("/"),
            llm_model=os.getenv("ARIADNE_LLM_MODEL", "qwen2.5:1.5b"),
            llm_api_key=os.getenv("ARIADNE_LLM_API_KEY", ""),
            llm_timeout=float(os.getenv("ARIADNE_LLM_TIMEOUT", "60")),
            query_timeout=float(os.getenv("ARIADNE_QUERY_TIMEOUT", "15")),
        )

    def validate(self) -> None:
        """Fail early for unsupported backends or insecure database setup."""
        if self.graph_backend not in {"memory", "neo4j"}:
            raise ValueError("ARIADNE_GRAPH_BACKEND must be memory or neo4j")
        if self.agent_mode not in {"auto", "llm", "deterministic"}:
            raise ValueError("ARIADNE_AGENT_MODE must be auto, llm or deterministic")
        if self.graph_backend == "neo4j" and not self.neo4j_password:
            raise ValueError("NEO4J_PASSWORD is required for the Neo4j backend")
        if self.agent_mode == "llm" and not self.llm_base_url:
            raise ValueError("ARIADNE_LLM_BASE_URL is required in llm mode")
