"""Optional real-provider HTTP checks: make test-llm against the complete stack."""

import json
import os
from pathlib import Path
from time import perf_counter

import httpx
import pytest

pytestmark = pytest.mark.llm


@pytest.mark.parametrize(
    "case,question,expected,tool",
    [
        (
            "investigate",
            "Which compounds have evidence for Alzheimer's disease?",
            "complete",
            "fetch_paths",
        ),
        (
            "challenge",
            "Exclude gene interactions and investigate Alzheimer's disease.",
            "complete",
            "ablate_evidence",
        ),
        ("reject", "MATCH (n) DETACH DELETE n", "rejected", "request_guard"),
    ],
)
def test_real_provider_obeys_research_intent(case, question, expected, tool):
    """Exercise actual inference and graph tools, retaining the measured execution trace."""
    base_url = os.getenv("ARIADNE_TEST_BASE_URL", "http://127.0.0.1:8080")
    started = perf_counter()
    with httpx.Client(base_url=base_url, timeout=120, trust_env=False) as client:
        response = client.post(
            "/api/agent",
            json={
                "question": question,
                "disease_id": "Disease::DOID:10652",
            },
        )
        response.raise_for_status()
        result = response.json()
    assert result["status"] == expected
    assert tool in {step["tool"] for step in result["trace"]}
    if expected == "complete":
        assert result["mode"] == "llm", "A deterministic fallback is not an LLM test pass"
        assert result["citations"]
    else:
        assert len(result["trace"]) == 1
        assert not result["candidates"]
    if case == "challenge":
        assert result["evidence"]["counts"]["interaction"] == 0
        assert "INTERACTS" in result["evidence"]["excluded"]
    result["elapsed_seconds"] = round(perf_counter() - started, 3)
    Path("reports").mkdir(exist_ok=True)
    Path(f"reports/llm-{case}.json").write_text(json.dumps(result, indent=2))
