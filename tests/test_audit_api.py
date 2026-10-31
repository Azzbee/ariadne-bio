"""HTTP audit and replay must preserve exact scope and reject ambiguous authority."""

import copy

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.service import EvidenceService
from tests.test_graph_engine import create_fixture_engine


@pytest.fixture(name="audit_client")
def _audit_client(tmp_path):
    """Use the same real typed graph in the API and the independent mathematical tests."""
    service = EvidenceService(Settings(), engine=create_fixture_engine(tmp_path))
    with TestClient(create_app(Settings(), service=service)) as client:
        yield client


def request_payload(**changes):
    """Name a supported candidate from the hand-counted fixture."""
    return {"disease_id": "Disease::D1", "compound_id": "Compound::C2", **changes}


def test_audit_and_verification_roundtrip_preserve_the_hashed_scientific_payload(audit_client):
    """Response validation must not add defaults or round a field inside the certificate."""
    response = audit_client.post("/api/audit", json=request_payload())
    assert response.status_code == 200, response.text
    certificate = response.json()
    assert certificate["baseline"]["supported"]
    assert certificate["scope"]["universe"] == "all_recorded_BINDS_edges"
    assert certificate["scope"]["includes_competitor_changes"] is True
    assert certificate["identity"]["scorer"] == "float64-fixed-order-v1"
    assert [row["budget"] for row in certificate["results"]] == [0, 1, 2]
    replay = audit_client.post("/api/audit/verify", json={"certificate": certificate})
    assert replay.status_code == 200, replay.text
    assert replay.json()["valid"] is True
    assert replay.json()["status"] == "verified"
    assert replay.json()["checks"]
    assert replay.json()["errors"] == []


def test_modified_certificates_cannot_borrow_a_verified_result(audit_client):
    """A digest is not enough: untrusted claims must be compared with recomputed results."""
    certificate = audit_client.post("/api/audit", json=request_payload()).json()
    for field, value in (("minimum_failure_budget", 99), ("top_k", 0), ("budget", 200)):
        altered = copy.deepcopy(certificate)
        altered[field] = value
        result = audit_client.post("/api/audit/verify", json={"certificate": altered})
        assert result.status_code == 200, result.text
        assert result.json()["valid"] is False
        assert result.json()["status"] == "invalid"
        assert result.json()["errors"]
    assert audit_client.post("/api/audit/verify", json={"certificate": {}}).json()["valid"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"budget": -1},
        {"budget": 3},
        {"budget": True},
        {"budget": "2"},
        {"top_k": 0},
        {"top_k": 101},
        {"top_k": 1.5},
        {"top_k": False},
        {"exclude": ["INTERACTS"]},
        {"operation": "DELETE"},
        {"compound_id": " "},
        {"disease_id": "x" * 181},
    ],
)
def test_invalid_or_unbounded_audit_requests_are_rejected(audit_client, changes):
    """The typed request cannot silently coerce a budget or inherit family exclusions."""
    assert audit_client.post("/api/audit", json=request_payload(**changes)).status_code == 422


def test_unknown_typed_entities_are_not_empty_successes(audit_client):
    """A missing or wrong-kind entity is a lookup error, not a robustness verdict."""
    for changes in ({"compound_id": "Disease::D1"}, {"disease_id": "Disease::missing"}):
        response = audit_client.post("/api/audit", json=request_payload(**changes))
        assert response.status_code == 404


def test_zero_budget_and_unsupported_candidates_are_explicit(audit_client):
    """No-edit bounds preserve rank and an isolated candidate never becomes supported."""
    response = audit_client.post("/api/audit", json=request_payload(budget=0, top_k=1))
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["results"]) == 1
    assert result["results"][0]["worst_supported_rank"] == result["baseline"]["rank"]
    unsupported = audit_client.post(
        "/api/audit", json=request_payload(compound_id="Compound::C0")
    ).json()
    assert unsupported["baseline"]["supported"] is False
    assert unsupported["baseline"]["rank"] is None
    assert unsupported["minimum_failure_budget"] == 0
    assert all(row["top_k_robust"] is False for row in unsupported["results"])


def test_verification_payload_is_bounded_and_rejects_other_instructions(audit_client):
    """The verifier accepts only a size-bounded certificate object."""
    for payload in (
        {"certificate": [], "write": True},
        {"certificate": {}, "approve": True},
        {"certificate": {"padding": "x" * 262_145}},
    ):
        assert audit_client.post("/api/audit/verify", json=payload).status_code == 422


def test_untrained_service_remains_readable_but_does_not_certify(tmp_path):
    """Model-independent endpoints keep working while audit requests fail clearly."""
    engine = create_fixture_engine(tmp_path)
    engine.model = None
    service = EvidenceService(Settings(), engine=engine)
    with TestClient(create_app(Settings(), service=service)) as client:
        assert client.get("/api/health").json()["dataset_ready"] is False
        response = client.post("/api/audit", json=request_payload())
        assert response.status_code == 503
        assert "make evaluate" in response.json()["detail"]
        assert client.post("/api/audit/verify", json={"certificate": {}}).status_code == 503


def test_openapi_documents_the_bounded_audit_contract(audit_client):
    """The published schema exposes the limits clients must honor."""
    specification = audit_client.get("/openapi.json").json()
    assert "/api/audit" in specification["paths"]
    assert "/api/audit/verify" in specification["paths"]
    properties = specification["components"]["schemas"]["AuditRequest"]["properties"]
    assert properties["budget"]["maximum"] == 2
    assert properties["top_k"]["maximum"] == 100
