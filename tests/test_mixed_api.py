"""Exercise joint audit scope, JSON transport, offline replay and API rejection."""

from copy import deepcopy
import json

from fastapi.testclient import TestClient
import pytest

from app.binding_audit import certificate_digest
from app.config import Settings
from app.main import create_app
from app.service import EvidenceService
from scripts.verify_audit import verify_file
from tests.test_provenance_api import provenance_fixture


@pytest.fixture(name="mixed_client")
def _mixed_client(tmp_path):
    service = EvidenceService(Settings(), engine=provenance_fixture(tmp_path))
    with TestClient(create_app(Settings(), service=service)) as client:
        yield client


def payload(**changes):
    """Use the same overlapping source/citation graph as the separate audit."""
    return {"disease_id": "Disease::D1", "compound_id": "Compound::C2", **changes}


def test_joint_api_preserves_sealed_frontier_and_offline_replay(mixed_client, tmp_path):
    """HTTP serialization and the public CLI must retain the exact proof object."""
    response = mixed_client.post("/api/mixed/audit", json=payload())
    assert response.status_code == 200, response.text
    certificate = response.json()
    assert certificate["method"] == "mixed-group-edge-envelope-v1"
    assert certificate_digest(certificate) == certificate["certificate_sha256"]
    assert {(row["group_budget"], row["edge_budget"]) for row in certificate["results"]} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    verified = mixed_client.post("/api/mixed/audit/verify", json={"certificate": certificate})
    assert verified.status_code == 200, verified.text
    assert verified.json()["valid"] is True
    assert verified.json()["replayed_witnesses"] >= 1
    exported = tmp_path / "joint-certificate.json"
    exported.write_text(json.dumps(certificate), encoding="utf-8")
    assert verify_file(exported, tmp_path)["valid"] is True


def test_joint_api_rejects_rehashed_false_frontier(mixed_client):
    """A transport-valid checksum never substitutes for mathematical replay."""
    certificate = mixed_client.post("/api/mixed/audit", json=payload()).json()
    altered = deepcopy(certificate)
    altered["results"][0]["worst_supported_rank"] = 999
    altered["certificate_sha256"] = certificate_digest(altered)
    response = mixed_client.post("/api/mixed/audit/verify", json={"certificate": altered})
    assert response.status_code == 200, response.text
    assert response.json()["valid"] is False
    assert response.json()["errors"]


def test_joint_api_respects_zero_budgets_and_explicit_pubmed_scope(mixed_client):
    """A narrower request cannot silently inherit the default attack rectangle."""
    response = mixed_client.post(
        "/api/mixed/audit",
        json=payload(group_kind="pubmed", group_ids=["pubmed:10001"], edge_budget=0),
    )
    assert response.status_code == 200, response.text
    certificate = response.json()
    assert len(certificate["results"]) == 2
    assert certificate["scope"]["group_ids"] == ["pubmed:10001"]
    assert all(row["edge_budget"] == 0 for row in certificate["results"])
    assert mixed_client.post("/api/mixed/audit/verify", json={"certificate": certificate}).json()[
        "valid"
    ]


@pytest.mark.parametrize(
    "changes",
    [
        {"group_budget": 2},
        {"edge_budget": 2},
        {"group_budget": -1},
        {"edge_budget": True},
        {"group_budget": "1"},
        {"edge_budget": 0.5},
        {"top_k": 0},
        {"top_k": 101},
        {"top_k": False},
        {"group_kind": "study"},
        {"group_kind": "pubmed"},
        {"group_ids": []},
        {"group_ids": ["source:Registry A"] * 2},
        {"group_ids": [f"source:{i}" for i in range(17)]},
        {"group_ids": ["pubmed:10001"]},
        {"group_ids": [42]},
        {"group_ids": ["source:nonexistent"]},
        {"group_ids": ["source:" + "x" * 241]},
        {"protected_group_ids": ["source:Registry A"]},
        {"exclude": ["INTERACTS"]},
        {"compound_id": " "},
    ],
)
def test_joint_api_bounds_its_declared_attack_space(mixed_client, changes):
    """Coercion, widened universes and unrelated family filters are rejected."""
    response = mixed_client.post("/api/mixed/audit", json=payload(**changes))
    assert response.status_code == 422, response.text


def test_joint_api_returns_missing_entity_and_model_errors(mixed_client, tmp_path):
    """Unavailable inputs cannot become an empty or vacuously successful audit."""
    response = mixed_client.post("/api/mixed/audit", json=payload(compound_id="Compound::missing"))
    assert response.status_code == 404
    (tmp_path / "unfitted").mkdir()
    engine = provenance_fixture(tmp_path / "unfitted")
    engine.model = None
    service = EvidenceService(Settings(), engine=engine)
    with TestClient(create_app(Settings(), service=service)) as client:
        response = client.post("/api/mixed/audit", json=payload())
        assert response.status_code == 503
