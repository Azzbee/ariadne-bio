"""Idempotent Neo4j ingestion: python -m scripts.load_neo4j."""

import json
from dotenv import load_dotenv

from app.config import Settings
from app.neo4j_repository import Neo4jRepository


def main() -> None:
    """Load the pinned evidence graph without any treatment-label edges."""
    load_dotenv()
    settings = Settings.from_env()
    if not settings.neo4j_password:
        raise ValueError("Set NEO4J_PASSWORD before importing")
    repository = Neo4jRepository(settings)
    try:
        print(json.dumps(repository.ingest(settings.data_dir), indent=2))
    finally:
        repository.close()


if __name__ == "__main__":
    main()
