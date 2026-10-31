"""Remove only prior operational outputs before collecting one CI job's evidence."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

RUN_REPORTS = (
    "http_smoke.json",
    "neo4j-junit.xml",
    "llm-junit.xml",
    "llm-investigate.json",
    "llm-challenge.json",
    "llm-reject.json",
    "llm-compound.json",
    "ollama-model.json",
    "container-logs.txt",
    "container-status.json",
    "runner-resources.txt",
    "docker-disk-usage.txt",
    "ci-integration.json",
)
QUALITY_OUTPUTS = (
    "coverage.xml",
    "reports/junit.xml",
    "demo.executed.ipynb",
    "data/processed/evaluation.json",
    "data/processed/model.json",
    "data/processed/manifest.json",
    "reports/ci-quality.json",
    "reports/v1.1.0/score-regression.json",
    "reports/v1.1.0/assessment-nicotine-interacts.json",
    "reports/v1.1.0/assessment-galantamine-interacts.json",
    "reports/v1.2.0/license-inventory.json",
    "reports/v1.2.0/binding-audit-benchmark.json",
    "reports/v1.2.0/binding-audit-summary.json",
    "reports/v1.2.0/binding-audit-example-competitor.json",
    "reports/v1.2.0/binding-audit-example-greedy.json",
    "reports/v1.2.0/binding-audit-example-strong-greedy.json",
    "reports/v1.2.0/binding-audit-example-scope.json",
)


def prepare_reports(root: Path, context: dict, job: str = "integration") -> None:
    """Invalidate old results only for the selected job; preserve graph/source files."""
    if job not in {"quality", "integration"}:
        raise ValueError("Evidence job must be quality or integration")
    outputs = (
        QUALITY_OUTPUTS if job == "quality" else tuple("reports/" + name for name in RUN_REPORTS)
    )
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    for name in outputs:
        (root / name).unlink(missing_ok=True)
    (reports / f"ci-{job}.json").write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """Record the checkout and Actions identifiers without reading any secrets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", choices=("quality", "integration"), required=True)
    arguments = parser.parse_args()
    context = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "checkout_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "repository": os.getenv("GITHUB_REPOSITORY"),
        "run_id": os.getenv("GITHUB_RUN_ID"),
        "run_attempt": os.getenv("GITHUB_RUN_ATTEMPT"),
        "job": arguments.job,
        "event": os.getenv("GITHUB_EVENT_NAME"),
        "status": "started; individual reports are written only by this run",
    }
    prepare_reports(Path.cwd(), context, arguments.job)


if __name__ == "__main__":
    main()
