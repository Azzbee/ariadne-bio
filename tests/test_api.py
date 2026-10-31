"""Exercise HTTP contracts against a hand-counted real graph engine."""

from dataclasses import replace
from unittest.mock import Mock

from fastapi.testclient import TestClient
from neo4j.exceptions import ServiceUnavailable
import pytest

from app.config import Settings
from app.main import create_app
from app.schemas import parse_exclusions
from app.service import EvidenceService
from tests.test_graph_engine import create_fixture_engine


@pytest.fixture
def service(tmp_path):
    """Use exact graph math and a known small model."""
    return EvidenceService(Settings(), engine=create_fixture_engine(tmp_path))


@pytest.fixture
def client(service):
    """Run the real FastAPI lifespan and dependency wiring."""
    with TestClient(create_app(Settings(), service=service)) as active:
        yield active


def test_health_and_openapi_are_real_and_report_execution_mode(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["dataset_ready"] is True
    assert response.json()["graph_backend"] == "memory"
    assert response.json()["agent_mode"] == "deterministic"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    spec = client.get("/openapi.json").json()
    assert "/api/evidence/{disease_id}/{compound_id}" in spec["paths"]
    assert "/api/assessment/{disease_id}/{compound_id}" in spec["paths"]
    assert "ChallengeRequest" in spec["components"]["schemas"]
    assert client.get("/docs").status_code == 200


def test_disease_lookup_paginates_and_handles_no_matches(client):
    first = client.get("/api/diseases", params={"limit": 1}).json()
    second = client.get("/api/diseases", params={"limit": 1, "offset": 1}).json()
    assert first["total"] == second["total"] == 2
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert client.get("/api/diseases?q=missing").json() == {"items": [], "total": 0}
    assert client.get("/api/diseases?limit=137").status_code == 200


def test_ranking_evidence_and_challenge_form_consistent_workflow(client):
    baseline = client.get("/api/rankings/Disease::D1?limit=3")
    assert baseline.status_code == 200
    assert baseline.json()["candidates"][0]["id"] == "Compound::C2"
    evidence = client.get("/api/evidence/Disease::D1/Compound::C2?limit=1").json()
    assert evidence["total_paths"] == 4
    assert len(evidence["paths"]) == 1
    assert evidence["truncated"] is True
    assert evidence["execution_backend"] == "memory"
    challenge = client.post(
        "/api/challenge",
        json={"disease_id": "Disease::D1", "exclude": ["INTERACTS"], "limit": 3},
    )
    assert challenge.status_code == 200
    result = challenge.json()
    assert result["before"][0]["id"] == "Compound::C2"
    assert result["after"][0]["id"] != "Compound::C2"
    assert all(row["features"]["interaction"] == 0 for row in result["after"])


def test_assessment_exposes_exact_terms_and_full_rank_outside_a_top_one_result(client):
    top = client.get("/api/rankings/Disease::D1?limit=1&exclude=INTERACTS").json()
    response = client.get("/api/assessment/Disease::D1/Compound::C2?exclude=interacts")
    assert response.status_code == 200
    assessment = response.json()
    assert top["candidates"][0]["id"] != assessment["compound"]["id"]
    assert assessment["baseline"]["rank"] == 1
    assert assessment["current"]["rank"] == 3
    assert assessment["delta"]["rank"] == -2
    assert assessment["excluded"] == ["INTERACTS"]
    decomposition = assessment["decomposition"]
    assert decomposition["reference"] == "training_mean"
    assert decomposition["units"] == "logit"
    assert len(decomposition["features"]) == 8
    assert assessment["current"]["logit"] == pytest.approx(
        decomposition["intercept"]
        + sum(term["contribution_after"] for term in decomposition["features"])
    )
    assert assessment["delta"]["logit"] == pytest.approx(
        sum(term["contribution_delta"] for term in decomposition["features"])
    )


def test_assessment_keeps_unsupported_diagnostics_distinct_from_supported_ranks(client):
    response = client.get("/api/assessment/Disease::D1/Compound::C1?exclude=BINDS")
    assert response.status_code == 200
    data = response.json()
    assert data["known_treatment"] is True
    assert data["current"]["supported"] is False
    assert data["current"]["rank"] is None
    assert data["current"]["score_status"] == "unsupported_diagnostic"
    assert 0 <= data["current"]["score"] <= 1
    assert data["current"]["evidence_count"] == 0
    assert data["delta"]["rank"] is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/diseases?limit=0",
        "/api/diseases?limit=138",
        "/api/diseases?offset=-1",
        "/api/rankings/Disease::D1?offset=-1",
        "/api/rankings/Disease::D1?limit=1000000",
        "/api/rankings/Disease::D1?exclude=TREATS",
        "/api/evidence/Disease::D1/Compound::C1?limit=31",
        "/api/evidence/Disease::D1/Compound::C1?exclude=INTERACTS,MATCH(n)",
        "/api/assessment/Disease::D1/Compound::C1?exclude=TREATS",
        "/api/similar/Compound::C1?algorithm=delete",
    ],
)
def test_invalid_parameters_are_rejected_before_unbounded_work(client, path):
    assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    "payload",
    [
        {"disease_id": "Disease::D1", "exclude": []},
        {"disease_id": "Disease::D1", "exclude": ["TREATS"]},
        {"disease_id": "Disease::D1", "exclude": ["INTERACTS"], "limit": 1000},
        {"disease_id": "Disease::D1", "exclude": ["INTERACTS"], "cypher": "DELETE n"},
    ],
)
def test_challenge_schema_rejects_unsupported_authority(client, payload):
    assert client.post("/api/challenge", json=payload).status_code == 422


def test_unknown_entities_are_clear_not_empty_successes(client):
    response = client.get("/api/rankings/Disease::unknown")
    assert response.status_code == 404
    assert "Unknown disease" in response.json()["detail"]
    assert client.get("/api/evidence/Disease::D1/Compound::unknown").status_code == 404
    assert client.get("/api/assessment/Disease::D1/Compound::unknown").status_code == 404
    assert client.get("/api/assessment/Compound::C1/Compound::C2").status_code == 404
    assert client.get("/api/algorithms/Compound::C1").status_code == 404


def test_algorithm_endpoints_and_manifest_preserve_provenance(client):
    assert client.get("/api/similar/Compound::C1").status_code == 200
    algorithms = client.get("/api/algorithms/Disease::D1")
    assert algorithms.status_code == 200
    assert algorithms.json()["execution_backend"] == "scipy-power-iteration"
    assert client.get("/api/provenance").json()["dataset_sha256"] == "fixture"
    assert client.get("/api/stats").json()["compounds"] == 4
    assert client.get("/api/stats").json()["diseases"] == 2
    assert client.get("/api/evaluation").json() == {"executed": True}


def test_missing_evaluation_is_actionable_service_unavailable(client, service, monkeypatch):
    monkeypatch.setattr(
        service.engine, "evaluation", Mock(side_effect=FileNotFoundError("missing"))
    )
    response = client.get("/api/evaluation")
    assert response.status_code == 503
    assert "make evaluate" in response.json()["detail"]


def test_database_failure_does_not_disclose_connection_details(client, service, monkeypatch):
    monkeypatch.setattr(
        service, "evidence", Mock(side_effect=ServiceUnavailable("password=must-not-leak"))
    )
    response = client.get("/api/evidence/Disease::D1/Compound::C2")
    assert response.status_code == 503
    assert "must-not-leak" not in response.text


def test_agent_endpoint_uses_compiled_graph_and_enforces_input_schema(client):
    result = client.post("/api/agent", json={"question": "Explain D1"})
    assert result.status_code == 200
    assert result.json()["status"] == "complete"
    assert result.json()["mode"] == "deterministic"
    assert result.json()["citations"]
    rejected = client.post("/api/agent", json={"question": "MATCH (n) DETACH DELETE n"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert client.post("/api/agent", json={"question": "x"}).status_code == 422
    assert client.post("/api/agent", json={"question": "x" * 2001}).status_code == 422
    assert (
        client.post("/api/agent", json={"question": "Explain D1", "write": True}).status_code == 422
    )


def test_agent_endpoint_preserves_compound_focus_and_assessment_contract(client):
    response = client.post(
        "/api/agent",
        json={
            "question": "Explain the selected compound",
            "disease_id": "Disease::D1",
            "compound_id": "Compound::C3",
            "exclude": ["INTERACTS"],
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert result["compound"]["id"] == "Compound::C3"
    assert result["assessment"]["compound"] == result["compound"]
    assert result["evidence"]["compound"] == result["compound"]
    assert result["assessment"]["excluded"] == ["INTERACTS"]
    assert result["candidates"][0]["id"] != result["compound"]["id"]
    for invalid in ({}, "x" * 181, "", "   "):
        rejected = client.post(
            "/api/agent", json={"question": "Explain D1", "compound_id": invalid}
        )
        assert rejected.status_code == 422


def test_service_closes_injected_repository_and_uses_live_paths(service):
    repository = Mock()
    repository.evidence.return_value = {
        "nodes": [],
        "edges": [],
        "paths": [],
        "execution_backend": "neo4j",
    }
    service.repository = repository
    evidence = service.evidence("Disease::D1", "Compound::C2", limit=2)
    assert evidence["total_paths"] == 4
    assert evidence["truncated"] is True
    assert evidence["execution_backend"] == "neo4j"
    repository.evidence.assert_called_once_with("Disease::D1", "Compound::C2", (), 2)
    repository.similar.return_value = {"items": [], "execution_backend": "neo4j"}
    assert service.similar("Compound::C1")["execution_backend"] == "neo4j"
    repository.gds_similarity.return_value = {"items": [], "execution_backend": "neo4j-gds"}
    assert service.similar("Compound::C1", algorithm="gds")["execution_backend"] == "neo4j-gds"
    repository.algorithms.return_value = {"execution_backend": "neo4j-gds"}
    assert service.algorithms("Disease::D1")["execution_backend"] == "neo4j-gds"
    service.close()
    repository.close.assert_called_once()


def test_settings_fail_closed_and_read_supported_environment(monkeypatch):
    for settings in (
        Settings(graph_backend="anything"),
        Settings(agent_mode="anything"),
        Settings(graph_backend="neo4j", neo4j_password=""),
        Settings(agent_mode="llm", llm_base_url=""),
    ):
        with pytest.raises(ValueError):
            settings.validate()
    monkeypatch.setenv("NEO4J_PASSWORD", "test-password")
    monkeypatch.setenv("ARIADNE_GRAPH_BACKEND", "neo4j")
    monkeypatch.setenv("ARIADNE_LLM_BASE_URL", "http://localhost:11434/v1/")
    monkeypatch.setenv("ARIADNE_LLM_TIMEOUT", "12.5")
    result = Settings.from_env()
    result.validate()
    assert result.llm_base_url == "http://localhost:11434/v1"
    assert result.llm_timeout == 12.5
    assert replace(result, agent_mode="deterministic").agent_mode == "deterministic"
    assert parse_exclusions(" interacts,PARTICIPATES,INTERACTS ") == ("INTERACTS", "PARTICIPATES")
