"""Exercise the main HTTP workflow against a real running ARIADNE stack."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import time
from urllib.parse import quote
import urllib.error
import urllib.request


def request(base_url: str, path: str, payload: dict | bytes | None = None) -> dict:
    """Request JSON and propagate connection, status and decoding failures."""
    data = (
        payload
        if isinstance(payload, bytes)
        else (json.dumps(payload).encode() if payload is not None else None)
    )
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def _expect_rejection(base_url, path, payload, status, message=None):
    """Require the intended boundary to reject a request, not a downstream accident."""
    try:
        request(base_url, path, payload)
    except urllib.error.HTTPError as error:
        with error:
            assert error.code == status, {"path": path, "expected": status, "actual": error.code}
            if message is not None:
                assert message in error.read().decode("utf-8"), path
        return status
    raise AssertionError(f"{path} accepted a request that must fail with HTTP {status}")


def verify_certificate_transport(base_url: str, certificates: dict) -> dict:
    """Replay real certificates through Nginx above the former 32 KiB wire limit."""
    checked = []
    for path, certificate in certificates.items():
        data = json.dumps({"certificate": certificate}, indent=2, ensure_ascii=False).encode()
        # Small certificates use legal JSON trailing whitespace to exercise the same boundary.
        data += b"\n" * max(0, 32_769 - len(data))
        assert 32_768 < len(data) < 1_048_576
        verification = request(base_url, path, data)
        assert verification["valid"] is True, {"path": path, "verification": verification}
        content_rejection = _expect_rejection(
            base_url,
            path,
            {"certificate": {"oversized": "x" * 262_144}},
            422,
            "256 KiB verification limit",
        )
        transport_rejection = _expect_rejection(base_url, path, b"{}" + b" " * 1_048_576, 413)
        checked.append(
            {
                "path": path,
                "valid_request_bytes": len(data),
                "certificate_sha256": certificate["certificate_sha256"],
                "valid": verification["valid"],
                "oversized_certificate_status": content_rejection,
                "oversized_transport_status": transport_rejection,
            }
        )
    ordinary = json.dumps({"question": "MATCH (n) DETACH DELETE n"}).encode() + b" " * 32_768
    ordinary_rejection = _expect_rejection(base_url, "/api/agent", ordinary, 413)
    return {
        "status": "passed",
        "verification_http_limit_bytes": 1_048_576,
        "parsed_certificate_limit_bytes": 262_144,
        "ordinary_http_limit_bytes": 32_768,
        "ordinary_oversized_request_status": ordinary_rejection,
        "requests": checked,
    }


def verify_core(base_url: str) -> dict:
    """Prove the default core stack uses Neo4j and deterministic tools without an LLM."""
    health = request(base_url, "/api/health")
    assert health["dataset_ready"] and health["graph_backend"] == "neo4j", health
    assert health["agent_mode"] == "deterministic", health
    investigation = request(
        base_url,
        "/api/agent",
        {
            "question": "Which compounds have evidence for asthma?",
            "disease_id": "Disease::DOID:2841",
        },
    )
    assert investigation["status"] == "complete", investigation
    assert investigation["mode"] == "deterministic", investigation
    assert investigation["citations"], investigation
    assert investigation["evidence"]["execution_backend"] == "neo4j", investigation
    return {"status": "passed", "health": health, "investigation": investigation}


def verify_frontend_headers(base_url: str) -> dict:
    """Check the served HTML and stylesheet, where Nginx inheritance can differ."""
    expected = {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-Frame-Options": "SAMEORIGIN",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }
    checked = {}
    for path in (
        "/",
        "/styles.css",
        "/audit.css",
        "/audit.js",
        "/provenance.css",
        "/provenance.js",
        "/landing.css",
        "/landing.js",
        "/mixed.js",
    ):
        req = urllib.request.Request(base_url.rstrip("/") + path, method="HEAD")
        with urllib.request.urlopen(req, timeout=15) as response:
            actual = {name: response.headers.get(name) for name in expected}
            assert actual == expected, {"path": path, "headers": actual}
            assert "no-cache" in response.headers.get("Cache-Control", ""), path
            checked[path] = actual
    return checked


def verify_assessment(assessment: dict) -> None:
    """Reconstruct both logistic scores from the exact returned linear terms."""
    decomposition = assessment["decomposition"]
    assert decomposition["reference"] == "training_mean"
    assert decomposition["units"] == "logit"
    for state, suffix in (("baseline", "before"), ("current", "after")):
        logit = decomposition["intercept"] + sum(
            feature[f"contribution_{suffix}"] for feature in decomposition["features"]
        )
        assert math.isclose(logit, assessment[state]["logit"], abs_tol=1e-10)
        score = (
            1 / (1 + math.exp(-logit)) if logit >= 0 else math.exp(logit) / (1 + math.exp(logit))
        )
        assert math.isclose(score, assessment[state]["score"], abs_tol=1e-10)
        if not assessment[state]["supported"]:
            assert assessment[state]["rank"] is None
            assert assessment[state]["score_status"] == "unsupported_diagnostic"
    assert math.isclose(
        sum(feature["contribution_delta"] for feature in decomposition["features"]),
        assessment["delta"]["logit"],
        abs_tol=1e-10,
    )


def _canonical_numbers(value):
    """Preserve JSON number meaning across a browser's binary64 round trip."""
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, int):
        if abs(value) > 2**53 - 1:
            raise ValueError("Certificate integers must be exactly representable in JSON clients")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Certificate numbers must be finite")
        if value.is_integer():
            return _canonical_numbers(int(value))
        return value
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("Certificate object keys must be strings")
        return {key: _canonical_numbers(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical_numbers(item) for item in value]
    raise ValueError("Certificate values must be JSON-compatible")


def _certificate_hash(certificate: dict) -> str:
    """Reproduce the public JSON hash without importing the scientific implementation."""
    payload = {key: value for key, value in certificate.items() if key != "certificate_sha256"}
    encoded = json.dumps(
        _canonical_numbers(payload),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def verify_binding_audit(base_url: str, disease_id: str, compound_id: str) -> dict:
    """Exercise certification, full verification and rejection of a rehashed false claim."""
    certificate = request(
        base_url,
        "/api/audit",
        {"disease_id": disease_id, "compound_id": compound_id, "top_k": 10, "budget": 2},
    )
    assert certificate["disease"]["id"] == disease_id
    assert certificate["compound"]["id"] == compound_id
    assert certificate["method"] == "binding-envelope-v1"
    assert certificate["identity"]["scorer"] == "decimal80-binary64-v1"
    assert certificate["scope"]["universe"] == "all_recorded_BINDS_edges"
    assert certificate["scope"]["includes_competitor_changes"] is True
    assert certificate["certificate_sha256"] == _certificate_hash(certificate)
    assert [row["budget"] for row in certificate["results"]] == [0, 1, 2]
    assert certificate["baseline"]["supported"] is True
    assert certificate["results"][0]["worst_supported_rank"] == certificate["baseline"]["rank"]
    edge_count = certificate["scope"]["eligible_edges"]
    assert certificate["proof"]["covered_global_states"] == sum(
        math.comb(edge_count, size) for size in range(min(2, edge_count) + 1)
    )
    for result in certificate["results"]:
        for field in ("rank_witness", "unsupported_witness"):
            witness = result[field]
            if witness is not None:
                assert len(set(witness["removed_edge_ids"])) == witness["deletions_used"]
                assert witness["deletions_used"] <= result["budget"]
                assert all(record["type"] == "BINDS" for record in witness["removed_records"])
    verification = request(base_url, "/api/audit/verify", {"certificate": certificate})
    assert verification["valid"] is True and verification["status"] == "verified", verification
    assert verification["errors"] == [] and verification["replayed_witnesses"] >= 1
    altered = json.loads(json.dumps(certificate))
    altered["results"][0]["worst_supported_rank"] += 1
    altered["certificate_sha256"] = _certificate_hash(altered)
    rejected = request(base_url, "/api/audit/verify", {"certificate": altered})
    assert rejected["valid"] is False and rejected["status"] == "invalid", rejected
    assert rejected["errors"], rejected
    return {
        "certificate": certificate,
        "verification": verification,
        "rehashed_false_claim": {
            "changed_field": "results[0].worst_supported_rank",
            "certificate_sha256": altered["certificate_sha256"],
            "verification": rejected,
        },
    }


def verify_mixed_audit(base_url: str, disease_id: str, compound_id: str) -> dict:
    """Verify the joint rectangle and reject a checksum-valid false frontier."""
    certificate = request(
        base_url,
        "/api/mixed/audit",
        {
            "disease_id": disease_id,
            "compound_id": compound_id,
            "top_k": 10,
            "group_budget": 1,
            "edge_budget": 1,
        },
    )
    assert certificate["method"] == "mixed-group-edge-envelope-v1"
    assert certificate["identity"]["scorer"] == "decimal80-binary64-v1"
    assert certificate["disease"]["id"] == disease_id
    assert certificate["compound"]["id"] == compound_id
    assert certificate["scope"]["includes_competitor_changes"] is True
    assert certificate["certificate_sha256"] == _certificate_hash(certificate)
    assert {(row["group_budget"], row["edge_budget"]) for row in certificate["results"]} == {
        (0, 0),
        (0, 1),
        (1, 0),
        (1, 1),
    }
    verification = request(base_url, "/api/mixed/audit/verify", {"certificate": certificate})
    assert verification["valid"] is True and verification["status"] == "verified", verification
    assert verification["errors"] == [] and verification["replayed_witnesses"] >= 1
    altered = json.loads(json.dumps(certificate))
    altered["results"][0]["worst_supported_rank"] += 1
    altered["certificate_sha256"] = _certificate_hash(altered)
    rejected = request(base_url, "/api/mixed/audit/verify", {"certificate": altered})
    assert rejected["valid"] is False and rejected["errors"], rejected
    return {
        "certificate": certificate,
        "verification": verification,
        "rehashed_false_claim": {
            "changed_field": "results[0].worst_supported_rank",
            "certificate_sha256": altered["certificate_sha256"],
            "verification": rejected,
        },
    }


def verify_provenance_audit(base_url: str, disease_id: str, compound_id: str) -> dict:
    """Exercise shared-group scope, exact protection, replay and checksum-valid forgery."""
    catalogue = request(base_url, "/api/provenance/groups?kind=source&limit=100")
    selected = sorted(group["group_id"] for group in catalogue["items"])
    assert catalogue["total"] == len(selected) <= 16
    assert catalogue["coverage"]["binding_edges"] > 0
    parameters = {
        "disease_id": disease_id,
        "compound_id": compound_id,
        "top_k": 10,
        "budget": 2,
    }
    certificate = request(base_url, "/api/provenance/audit", parameters)
    assert certificate["method"] == "provenance-group-exhaustive-v1"
    assert certificate["identity"]["scorer"] == "decimal80-binary64-v1"
    assert certificate["scope"]["operation"] == "withdraw_records_mentioning_any_selected_group"
    assert certificate["scope"]["group_ids"] == selected
    assert certificate["scope"]["includes_competitor_changes"] is True
    assert certificate["identity"]["group_map_sha256"] == catalogue["identity"]["group_map_sha256"]
    assert certificate["certificate_sha256"] == _certificate_hash(certificate)
    assert [row["budget"] for row in certificate["results"]] == [0, 1, 2]
    assert certificate["proof"]["covered_scenarios"] == sum(
        math.comb(len(selected), size) for size in range(min(2, len(selected)) + 1)
    )
    verified = request(base_url, "/api/provenance/audit/verify", {"certificate": certificate})
    assert verified["valid"] is True and verified["replayed_witnesses"] >= 1, verified

    altered = json.loads(json.dumps(certificate))
    plan = altered["protection_plan"]
    plan["minimum_additional_groups"] = (plan["minimum_additional_groups"] or 0) + 1
    altered["certificate_sha256"] = _certificate_hash(altered)
    rejected = request(base_url, "/api/provenance/audit/verify", {"certificate": altered})
    assert rejected["valid"] is False and rejected["errors"], rejected
    assert "Certificate content checksum matches" in rejected["checks"], rejected

    protected = certificate["protection_plan"]["representative"]
    assert certificate["protection_plan"]["status"] != "impossible_baseline"
    conditional = request(
        base_url,
        "/api/provenance/audit",
        {**parameters, "group_ids": selected, "protected_group_ids": protected},
    )
    assert conditional["results"][-1]["robust"] is True
    assert conditional["protection_plan"]["status"] == "already_robust"
    conditional_verified = request(
        base_url, "/api/provenance/audit/verify", {"certificate": conditional}
    )
    assert conditional_verified["valid"] is True, conditional_verified

    citations = request(base_url, "/api/provenance/groups?kind=pubmed&limit=1")
    assert citations["items"], citations
    citation = request(
        base_url,
        "/api/provenance/audit",
        {
            **parameters,
            "group_kind": "pubmed",
            "group_ids": [citations["items"][0]["group_id"]],
            "budget": 1,
        },
    )
    assert citation["proof"]["covered_scenarios"] == 2
    citation_verified = request(base_url, "/api/provenance/audit/verify", {"certificate": citation})
    assert citation_verified["valid"] is True, citation_verified
    return {
        "certificate": certificate,
        "verification": verified,
        "rehashed_false_protection_claim": rejected,
        "conditional_certificate": conditional,
        "conditional_verification": conditional_verified,
        "selected_pubmed_certificate": citation,
        "selected_pubmed_verification": citation_verified,
    }


def run(base_url: str) -> dict:
    """Assert healthy data, real evidence, a changed exclusion and safe agent behavior."""
    started = time.perf_counter()
    headers = verify_frontend_headers(base_url)
    health = request(base_url, "/api/health")
    assert health.get("dataset_ready"), health
    diseases = request(base_url, "/api/diseases?limit=100")
    assert diseases["items"], diseases
    disease = next(
        (item for item in diseases["items"] if "asthma" in item["name"].lower()),
        diseases["items"][0],
    )
    identifier = quote(disease["id"], safe="")
    ranking = request(base_url, f"/api/rankings/{identifier}?limit=5")
    assert ranking["candidates"], ranking
    compound = ranking["candidates"][0]
    compound_identifier = quote(compound["id"], safe="")
    evidence = request(base_url, f"/api/evidence/{identifier}/{compound_identifier}?limit=8")
    assert evidence["nodes"] and evidence["paths"], evidence
    challenge = request(
        base_url,
        "/api/challenge",
        {"disease_id": disease["id"], "exclude": ["INTERACTS"], "limit": 5},
    )
    assert "INTERACTS" in challenge["excluded"], challenge
    assessment_path = f"/api/assessment/{identifier}/{compound_identifier}"
    assessment = request(base_url, assessment_path + "?exclude=INTERACTS")
    verify_assessment(assessment)
    assert assessment["compound"]["id"] == compound["id"]
    assert assessment["current"]["features"]["interaction"] == 0
    unsupported = request(base_url, assessment_path + "?exclude=BINDS")
    verify_assessment(unsupported)
    assert not unsupported["current"]["supported"]
    assert unsupported["current"]["evidence_count"] == 0
    audit = verify_binding_audit(base_url, disease["id"], compound["id"])
    provenance_audit = verify_provenance_audit(base_url, disease["id"], compound["id"])
    mixed_audit = verify_mixed_audit(base_url, disease["id"], compound["id"])
    certificate_transport = verify_certificate_transport(
        base_url,
        {
            "/api/audit/verify": audit["certificate"],
            "/api/provenance/audit/verify": provenance_audit["certificate"],
            "/api/mixed/audit/verify": mixed_audit["certificate"],
        },
    )
    rejected = request(
        base_url,
        "/api/agent",
        {"question": "MATCH (n) DETACH DELETE n", "disease_id": disease["id"]},
    )
    assert rejected["status"] == "rejected", rejected
    evaluation = request(base_url, "/api/evaluation")
    assert evaluation.get("metrics"), evaluation
    return {
        "status": "passed",
        "base_url": base_url,
        "health": health,
        "frontend_security_headers": headers,
        "assessment": {
            "compound_id": assessment["compound"]["id"],
            "fixed_model_sha256": assessment["model"]["model_sha256"],
            "exact_score_reconstruction": "passed",
            "unsupported_pair_retained": True,
        },
        "binding_audit": audit,
        "provenance_audit": provenance_audit,
        "mixed_audit": mixed_audit,
        "certificate_transport": certificate_transport,
        "disease": disease,
        "compound": {"id": compound["id"], "name": compound["name"]},
        "displayed_paths": len(evidence["paths"]),
        "agent_rejection": rejected["status"],
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def main() -> None:
    """Write machine-readable smoke evidence only after all assertions pass."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8080")
    parser.add_argument("--output", default="reports/http_smoke.json")
    parser.add_argument(
        "--core-only", action="store_true", help="Check default deterministic Neo4j startup"
    )
    arguments = parser.parse_args()
    report = verify_core(arguments.base_url) if arguments.core_only else run(arguments.base_url)
    path = Path(arguments.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
