"""Exercise the main HTTP workflow against a real running ARIADNE stack."""

import argparse
import json
from pathlib import Path
import time
from urllib.parse import quote
import urllib.request


def request(base_url: str, path: str, payload: dict | None = None) -> dict:
    """Request JSON and propagate connection, status and decoding failures."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def run(base_url: str) -> dict:
    """Assert healthy data, real evidence, a changed exclusion and safe agent behavior."""
    started = time.perf_counter()
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
    arguments = parser.parse_args()
    report = run(arguments.base_url)
    path = Path(arguments.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
