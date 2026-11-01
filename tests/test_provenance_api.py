"""HTTP scope, transport and verification tests for correlated record groups."""

from copy import deepcopy

from fastapi.testclient import TestClient
import pytest

from app.binding_audit import certificate_digest
from app.config import Settings
from app.main import create_app
from app.service import EvidenceService
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def provenance_fixture(tmp_path):
    """Overlapping imported labels are explicit; no independent-support mapping exists."""
    graph = tiny_graph()
    bindings = [edge for edge in graph["edges"] if edge["type"] == "BINDS"]
    for edge, sources, citations in zip(
        bindings,
        (["Registry A"], ["Registry A", "Registry B"], ["Registry B"]),
        (["10001"], ["10001", "10002"], ["10002"]),
    ):
        edge["sources"] = sources
        edge["data"]["pubmed_ids"] = citations
    return create_fixture_engine(tmp_path, graph)


@pytest.fixture(name="provenance_client")
def _provenance_client(tmp_path):
    service = EvidenceService(Settings(), engine=provenance_fixture(tmp_path))
    with TestClient(create_app(Settings(), service=service)) as client:
        yield client


def payload(**changes):
    """Use a candidate that has both directly shared imported source labels."""
    return {"disease_id": "Disease::D1", "compound_id": "Compound::C2", **changes}


def test_api_preserves_the_complete_sealed_certificate(provenance_client):
    """Pydantic serialization must not change a verifiable claim or add a default."""
    response = provenance_client.post("/api/provenance/audit", json=payload())
    assert response.status_code == 200, response.text
    certificate = response.json()
    assert certificate["method"] == "provenance-group-exhaustive-v1"
    assert certificate_digest(certificate) == certificate["certificate_sha256"]
    assert [row["budget"] for row in certificate["results"]] == [0, 1, 2]
    result = provenance_client.post(
        "/api/provenance/audit/verify", json={"certificate": certificate}
    )
    assert result.status_code == 200, result.text
    assert result.json()["valid"] is True
    assert result.json()["errors"] == []


def test_pubmed_selection_is_explicit_and_replayable(provenance_client):
    """A citation audit covers only the selected imported identifiers."""
    response = provenance_client.post(
        "/api/provenance/audit",
        json=payload(group_kind="pubmed", group_ids=["pubmed:10001"], budget=1),
    )
    assert response.status_code == 200, response.text
    certificate = response.json()
    assert len(certificate["results"]) == 2
    assert certificate["results"][1]["unsupported_attainable"] is True
    assert provenance_client.post(
        "/api/provenance/audit/verify", json={"certificate": certificate}
    ).json()["valid"]


def test_protection_changes_the_scenario_universe_and_the_seal(provenance_client):
    """Protecting every selected label leaves exactly the unchanged-graph outcome."""
    baseline = provenance_client.post("/api/provenance/audit", json=payload()).json()
    response = provenance_client.post(
        "/api/provenance/audit",
        json=payload(protected_group_ids=["source:Registry A", "source:Registry B"]),
    )
    assert response.status_code == 200, response.text
    conditional = response.json()
    assert conditional["certificate_sha256"] != baseline["certificate_sha256"]
    assert all(row["robust"] for row in conditional["results"])
    assert all(
        row["worst_supported_rank"] == conditional["baseline"]["rank"]
        for row in conditional["results"]
    )
    assert provenance_client.post(
        "/api/provenance/audit/verify", json={"certificate": conditional}
    ).json()["valid"]


def test_correctly_rehashed_false_claims_are_rejected(provenance_client):
    """A caller cannot replace a failed audit with a checksum-valid success."""
    certificate = provenance_client.post("/api/provenance/audit", json=payload()).json()
    altered = deepcopy(certificate)
    altered["results"][-1]["robust"] = True
    altered["results"][-1]["unsupported_attainable"] = False
    altered["certificate_sha256"] = certificate_digest(altered)
    response = provenance_client.post("/api/provenance/audit/verify", json={"certificate": altered})
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is False
    assert response.json()["errors"]


@pytest.mark.parametrize(
    "changes",
    [
        {"budget": -1},
        {"budget": 3},
        {"budget": True},
        {"budget": "1"},
        {"top_k": 0},
        {"top_k": 101},
        {"top_k": 1.5},
        {"top_k": False},
        {"group_kind": "study"},
        {"group_kind": "pubmed"},
        {"group_ids": []},
        {"group_ids": ["source:Registry A"] * 2},
        {"group_ids": [f"source:{index}" for index in range(17)]},
        {"group_ids": ["pubmed:10001"]},
        {"group_ids": [42]},
        {"group_ids": ["source:" + "x" * 241]},
        {"protected_group_ids": ["source:Registry A"] * 2},
        {"group_ids": ["source:Registry A"], "protected_group_ids": ["source:Registry B"]},
        {"protected_group_ids": ["pubmed:10001"]},
        {"exclude": ["INTERACTS"]},
        {"withdrawal_policy": "independent_or"},
        {"compound_id": " "},
    ],
)
def test_invalid_or_ambiguous_scope_is_rejected(provenance_client, changes):
    """No unbounded universe, implicit support policy or coerced numerical scope."""
    response = provenance_client.post("/api/provenance/audit", json=payload(**changes))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "changes",
    [{"disease_id": "Disease::missing"}, {"compound_id": "Gene::G1"}],
)
def test_unknown_typed_entities_are_not_certified(provenance_client, changes):
    assert (
        provenance_client.post("/api/provenance/audit", json=payload(**changes)).status_code == 404
    )


def test_untrained_graph_catalogue_remains_available(tmp_path):
    """Metadata inventory is not a fitted-model calculation."""
    engine = provenance_fixture(tmp_path)
    engine.model = None
    service = EvidenceService(Settings(), engine=engine)
    with TestClient(create_app(Settings(), service=service)) as client:
        catalogue = client.get("/api/provenance/groups")
        assert catalogue.status_code == 200, catalogue.text
        assert client.get("/api/provenance/groups?kind=pubmed&q=10001").status_code == 200
        assert client.post("/api/provenance/audit", json=payload()).status_code == 503
        assert (
            client.post("/api/provenance/audit/verify", json={"certificate": {}}).status_code == 503
        )


@pytest.mark.parametrize("query", ["kind=study", "limit=0", "limit=101", "offset=-1"])
def test_catalogue_bounds_are_explicit(provenance_client, query):
    assert provenance_client.get(f"/api/provenance/groups?{query}").status_code == 422


def test_verifier_cannot_accept_unbounded_or_extra_instructions(provenance_client):
    for request in (
        {"certificate": {}, "write": True},
        {"certificate": []},
        {"certificate": {"padding": "x" * 262_145}},
    ):
        assert (
            provenance_client.post("/api/provenance/audit/verify", json=request).status_code == 422
        )


def test_openapi_declares_the_complete_group_bound(provenance_client):
    schema = provenance_client.get("/openapi.json").json()
    assert "/api/provenance/groups" in schema["paths"]
    assert "/api/provenance/audit/verify" in schema["paths"]
    properties = schema["components"]["schemas"]["ProvenanceAuditRequest"]["properties"]
    assert properties["budget"]["maximum"] == 2
    assert properties["protected_group_ids"]["maxItems"] == 16


def test_container_smoke_gate_exercises_the_actual_typed_api(provenance_client, monkeypatch):
    """The same gate used by Docker must run through routes and detect a false optimum."""
    from infra import smoke  # pylint: disable=import-outside-toplevel

    def request(_base, path, body=None):
        response = (
            provenance_client.get(path) if body is None else provenance_client.post(path, json=body)
        )
        assert response.status_code == 200, response.text
        return response.json()

    monkeypatch.setattr(smoke, "request", request)
    report = smoke.verify_provenance_audit("http://testserver", "Disease::D1", "Compound::C2")
    assert report["verification"]["valid"] is True
    assert report["rehashed_false_protection_claim"]["valid"] is False
    assert report["conditional_verification"]["valid"] is True
    assert report["selected_pubmed_verification"]["valid"] is True
