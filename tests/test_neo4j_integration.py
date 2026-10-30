"""Real Neo4j/GDS checks against the pinned public dataset, never a mocked driver."""

import json
import math
from pathlib import Path

from dotenv import load_dotenv
from neo4j.exceptions import ConstraintError
import pytest

from app.config import Settings
from app.graph_engine import GraphEngine
from app.neo4j_repository import Neo4jRepository, PATH_QUERIES

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def real_graph():
    """Use only the explicitly configured development/test Neo4j instance."""
    load_dotenv()
    settings = Settings.from_env()
    if not settings.neo4j_password:
        pytest.skip("Set NEO4J_PASSWORD and run make docker-core before integration tests")
    repository = Neo4jRepository(settings)
    engine = GraphEngine(settings.data_dir)
    repository.verify(engine.manifest["dataset_sha256"])
    yield repository, engine
    repository.close()


def test_import_is_idempotent_and_labels_never_enter_evidence(real_graph):
    """A full second import cannot duplicate records or leak treatment labels."""
    repository, engine = real_graph
    before = repository.run("MATCH(n:Entity) RETURN count(n) AS nodes")[0]["nodes"]
    repository.ingest(engine.data_dir)
    after = repository.run("MATCH(n:Entity) RETURN count(n) AS nodes")[0]["nodes"]
    assert before == after == engine.manifest["nodes"]
    types = repository.run("MATCH ()-[r]->() RETURN type(r) AS type,count(r) AS count")
    assert {row["type"]: row["count"] for row in types} == engine.manifest["edge_counts"]
    assert not {"TREATS", "PALLIATES"} & {row["type"] for row in types}


@pytest.mark.parametrize(
    "disease_id,compound_id",
    [
        ("Disease::DOID:10652", "Compound::DB00674"),
        ("Disease::DOID:10652", "Compound::DB00184"),
    ],
)
def test_exact_cypher_path_counts_agree_with_independent_sparse_algebra(
    real_graph, disease_id, compound_id
):
    """Count every path in Cypher, independently of the matrix feature implementation."""
    repository, engine = real_graph
    evidence = engine.evidence(disease_id, compound_id)
    for family, query in PATH_QUERIES.items():
        count_query = query.replace("RETURN p LIMIT $limit", "RETURN count(p) AS count")
        count = repository.run(count_query, {"disease": disease_id, "compound": compound_id})
        assert count[0]["count"] == evidence["counts"][family]


def test_excluded_relationships_are_absent_from_real_neo4j_paths(real_graph):
    """An ablated explanation cannot quietly display forbidden evidence."""
    repository, _ = real_graph
    evidence = repository.evidence(
        "Disease::DOID:10652", "Compound::DB00674", exclude=("INTERACTS",), limit=12
    )
    assert evidence["paths"]
    assert all(edge["type"] != "INTERACTS" for edge in evidence["edges"])
    assert all(len(path["node_ids"]) == len(set(path["node_ids"])) for path in evidence["paths"])
    assert (
        repository.evidence("Disease::DOID:10652", "Compound::DB00674", exclude=("BINDS",))["paths"]
        == []
    )


def test_unique_constraint_rejects_duplicate_identity(real_graph):
    """An invalid duplicate write rolls back at the database constraint boundary."""
    repository, _ = real_graph
    with pytest.raises(ConstraintError):
        repository.run("CREATE (:Entity {id:$id})", {"id": "Compound::DB00674"}, write=True)


def test_parameterized_identifiers_cannot_turn_into_query_code(real_graph):
    """A hostile identifier is treated as data and does not match or mutate nodes."""
    repository, _ = real_graph
    malicious = "x'}) DETACH DELETE n //"
    result = repository.evidence("Disease::DOID:10652", malicious)
    assert result["paths"] == []
    assert repository.verify()["nodes"] == 24456


def test_real_gds_pagerank_and_target_similarity(real_graph):
    """Verify both algorithms and compare Jaccard against an independent calculation."""
    repository, engine = real_graph
    page_rank = repository.algorithms("Disease::DOID:10652", limit=5)
    assert page_rank["execution_backend"] == "neo4j-gds"
    assert page_rank["version"] == "2.13.4"
    assert len(page_rank["items"]) == 5
    assert all(math.isfinite(row["score"]) and row["score"] > 0 for row in page_rank["items"])
    gds = repository.gds_similarity("Compound::DB00674", limit=5)
    cypher = repository.similar("Compound::DB00674", limit=5)
    local = engine.similar("Compound::DB00674", limit=5)
    assert [row["id"] for row in gds["items"]] == [row["id"] for row in cypher["items"]]
    local_by_id = {row["id"]: row["similarity"] for row in local["items"]}
    for row in gds["items"]:
        assert row["similarity"] == pytest.approx(local_by_id[row["id"]])


def test_profile_proves_index_use_and_reduces_database_work(real_graph):
    """Use query-plan dbHits rather than noisy timing alone to establish the improvement."""
    repository, _ = real_graph
    report = repository.profile_lookup("Compound::DB00674")

    def operators(plan):
        return [plan.get("operatorType", "")] + [
            value for child in plan.get("children", []) for value in operators(child)
        ]

    def hits(plan):
        return plan.get("dbHits", 0) + sum(hits(child) for child in plan.get("children", []))

    assert any("IndexSeek" in operator for operator in operators(report["indexed"]["profile"]))
    assert hits(report["indexed"]["profile"]) < hits(report["scan"]["profile"])
    for variant in report.values():
        variant["total_db_hits"] = hits(variant["profile"])
        variant["operators"] = operators(variant["profile"])
    report["protocol"] = "Seven warm local round trips per equivalent query; one PROFILE run."
    Path("reports").mkdir(exist_ok=True)
    Path("reports/query_optimization.json").write_text(json.dumps(report, indent=2))
