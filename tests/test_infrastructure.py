"""Security and lifecycle tests for first-run setup and stack configuration."""

import importlib.util
import json
from pathlib import Path
import stat
import subprocess

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str):
    """Load a standalone infrastructure utility without modifying import paths."""
    spec = importlib.util.spec_from_file_location(name, ROOT / "infra" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_first_run_credentials_are_private_unique_and_never_overwritten(tmp_path):
    """Repeated setup must neither replace a secret nor make it world-readable."""
    setup = load_module("init_env")
    (tmp_path / ".env.example").write_text("NEO4J_PASSWORD=\nWEB_PORT=8080\n")
    assert setup.create_environment(tmp_path)
    first = (tmp_path / ".env").read_text()
    assert len(first.splitlines()[0].split("=", 1)[1]) >= 32
    assert stat.S_IMODE((tmp_path / ".env").stat().st_mode) == 0o600
    assert not setup.create_environment(tmp_path)
    assert (tmp_path / ".env").read_text() == first
    second = tmp_path / "another-checkout"
    second.mkdir()
    (second / ".env.example").write_text("NEO4J_PASSWORD=\n")
    assert setup.create_environment(second)
    assert (second / ".env").read_text().splitlines()[0] != first.splitlines()[0]


def test_clean_preserves_credentials_data_and_scientific_results(tmp_path):
    """Routine cleanup is deliberately incapable of deleting retained experiments."""
    cleaner = load_module("clean")
    protected = [".env", "data/processed/graph.json", "reports/evaluation.json", "app/main.py"]
    for filename in protected + ["app/__pycache__/main.pyc", "reports/junit.xml", ".coverage"]:
        path = tmp_path / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("keep" if filename in protected else "generated")
    cleaner.clean(tmp_path)
    assert all((tmp_path / filename).read_text() == "keep" for filename in protected)
    assert not (tmp_path / "app/__pycache__").exists()
    assert not (tmp_path / ".coverage").exists()


def test_database_is_private_and_api_waits_for_real_health():
    """A clean Compose start must require a secret and an available GDS database."""
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = compose["services"]
    assert all(port.startswith("127.0.0.1:") for port in services["neo4j"]["ports"])
    assert "${NEO4J_PASSWORD:?" in services["neo4j"]["environment"]["NEO4J_AUTH"]
    assert services["api"]["depends_on"]["neo4j"]["condition"] == "service_healthy"
    assert "gds.version()" in services["neo4j"]["healthcheck"]["test"][1]
    assert services["frontend"]["depends_on"]["api"]["condition"] == "service_healthy"


def test_help_and_entrypoint_are_valid_without_services():
    """Reviewers can discover commands before installing Docker or graph data."""
    help_result = subprocess.run(
        ["make", "help"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    assert "docker-run" in help_result.stdout and "test-integration" in help_result.stdout
    subprocess.run(["sh", "-n", "infra/entrypoint.sh"], cwd=ROOT, check=True)


class ModelInventory:
    """Controlled Ollama protocol boundary with observable pulls."""

    def __init__(self, inventories, pull_result=None):
        self.inventories = list(inventories)
        self.pull_result = pull_result or {"status": "success"}
        self.calls = []

    def request(self, path, payload=None):
        """Return the next actual inventory state or the simulated pull outcome."""
        self.calls.append((path, payload))
        if path == "/api/tags":
            return {"models": self.inventories.pop(0)}
        assert path == "/api/pull"
        return self.pull_result


def test_default_model_is_verified_and_repeat_run_never_pulls():
    """An existing exact model remains unchanged across repeat startup."""
    bootstrap = load_module("bootstrap_model")
    model = {"name": bootstrap.DEFAULT_MODEL, "digest": bootstrap.DEFAULT_MODEL_DIGEST, "size": 123}
    api = ModelInventory([[model], [model]])
    first = bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL)
    second = bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL)
    assert first["status"] == second["status"] == "verified"
    assert first["digest"] == second["digest"] == bootstrap.DEFAULT_MODEL_DIGEST
    assert first["reused_existing_model"] and second["reused_existing_model"]
    assert all(path == "/api/tags" for path, _ in api.calls)


def test_existing_model_mismatch_stops_without_overwriting():
    """A different local model cannot silently replace the reviewed reference."""
    bootstrap = load_module("bootstrap_model")
    model = {"name": bootstrap.DEFAULT_MODEL, "digest": "a" * 64}
    api = ModelInventory([[model]])
    with pytest.raises(bootstrap.ModelIdentityError, match="identity mismatch") as failure:
        bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL)
    assert failure.value.report["digest"] == "a" * 64
    assert failure.value.report["status"] == "failed"
    assert failure.value.report["expected_digest"] == bootstrap.DEFAULT_MODEL_DIGEST
    assert api.calls == [("/api/tags", None)]


def test_missing_model_is_pulled_once_then_full_identity_is_checked():
    """A first run downloads only the absent requested model and checks the result."""
    bootstrap = load_module("bootstrap_model")
    model = {"name": bootstrap.DEFAULT_MODEL, "digest": bootstrap.DEFAULT_MODEL_DIGEST}
    api = ModelInventory([[], [model]])
    result = bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL)
    assert not result["reused_existing_model"]
    assert result["status"] == "verified"
    assert api.calls == [
        ("/api/tags", None),
        ("/api/pull", {"model": bootstrap.DEFAULT_MODEL, "stream": False}),
        ("/api/tags", None),
    ]


def test_downloaded_model_mismatch_is_not_accepted_or_retried():
    """A changed upstream tag fails the first-run gate despite a successful pull."""
    bootstrap = load_module("bootstrap_model")
    api = ModelInventory([[], [{"name": bootstrap.DEFAULT_MODEL, "digest": "b" * 64}]])
    with pytest.raises(bootstrap.ModelIdentityError, match="identity mismatch"):
        bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL)
    assert sum(path == "/api/pull" for path, _ in api.calls) == 1


def test_custom_model_is_explicitly_unpinned_unless_a_digest_is_supplied():
    """Custom providers remain usable without claiming reference reproducibility."""
    bootstrap = load_module("bootstrap_model")
    model = {"name": "custom:latest", "digest": "c" * 64}
    api = ModelInventory([[model], [model]])
    unpinned = bootstrap.prepare_model(api, "custom")
    assert unpinned["status"] == "recorded_unpinned"
    assert unpinned["expected_digest"] is None
    assert "not a pinned reproduction" in unpinned["reproducibility"]
    pinned = bootstrap.prepare_model(api, "custom", "sha256:" + "c" * 64)
    assert pinned["status"] == "verified"
    assert all(path == "/api/tags" for path, _ in api.calls)


def test_model_pull_failure_never_becomes_verified():
    """An incomplete or failed model download cannot produce successful evidence."""
    bootstrap = load_module("bootstrap_model")
    api = ModelInventory([[]], {"status": "downloading"})
    with pytest.raises(bootstrap.ModelIdentityError, match="successful model download"):
        bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL)


def test_model_digest_must_be_full_before_any_network_call():
    """A truncated display ID is insufficient to reproduce a model."""
    bootstrap = load_module("bootstrap_model")
    api = ModelInventory([])
    with pytest.raises(bootstrap.ModelIdentityError, match="64 hexadecimal"):
        bootstrap.prepare_model(api, bootstrap.DEFAULT_MODEL, "65ec06548149")
    assert api.calls == []


def test_ci_evidence_starts_fresh_and_preserves_scientific_reports(tmp_path):
    """A failed new integration run cannot reuse historical operational successes."""
    evidence = load_module("prepare_ci_evidence")
    reports = tmp_path / "reports"
    reports.mkdir()
    for name in evidence.RUN_REPORTS:
        (reports / name).write_text('{"status":"old success"}')
    protected = [
        "reports/evaluation.json",
        "reports/ci-quality.json",
        "data/processed/graph.json",
        "data/processed/model.json",
        "data/processed/evaluation.json",
        "data/processed/manifest.json",
    ]
    for name in protected:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("scientific reference")
    evidence.prepare_reports(tmp_path, {"checkout_sha": "new-run", "status": "started"})
    assert all(
        not (reports / name).exists()
        for name in evidence.RUN_REPORTS
        if name != "ci-integration.json"
    )
    assert all((tmp_path / name).read_text() == "scientific reference" for name in protected)
    assert json.loads((reports / "ci-integration.json").read_text())["checkout_sha"] == "new-run"


def test_quality_evidence_removes_only_outputs_that_this_job_rebuilds(tmp_path):
    """A copied checkout cannot upload old trained artifacts after an early failure."""
    evidence = load_module("prepare_ci_evidence")
    for name in evidence.QUALITY_OUTPUTS:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("stale success")
    protected = [
        "data/processed/graph.json",
        "data/raw/input.bz2",
        "demo.ipynb",
        "app/main.py",
        "reports/evaluation.json",
        "reports/ci-integration.json",
    ]
    for name in protected:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("preserved source or independent evidence")
    evidence.prepare_reports(
        tmp_path, {"checkout_sha": "current-quality", "job": "quality"}, "quality"
    )
    assert all(
        not (tmp_path / name).exists()
        for name in evidence.QUALITY_OUTPUTS
        if name != "reports/ci-quality.json"
    )
    assert all(
        (tmp_path / name).read_text() == "preserved source or independent evidence"
        for name in protected
    )
    assert (
        json.loads((tmp_path / "reports/ci-quality.json").read_text())["checkout_sha"]
        == "current-quality"
    )


def test_model_failure_report_records_actual_digest_and_nonzero_exit(monkeypatch, capsys):
    """CLI evidence must identify the mismatch without declaring a successful gate."""
    bootstrap = load_module("bootstrap_model")
    actual = "d" * 64
    api = ModelInventory([[{"name": bootstrap.DEFAULT_MODEL, "digest": actual}]])
    monkeypatch.setattr(bootstrap, "OllamaAPI", lambda _base: api)
    monkeypatch.setattr("sys.argv", ["bootstrap_model.py", "--model", bootstrap.DEFAULT_MODEL])
    assert bootstrap.main() == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["status"] == "failed"
    assert report["digest"] == actual
    assert report["expected_digest"] == bootstrap.DEFAULT_MODEL_DIGEST
    assert "no existing model was overwritten" in output.err


def test_assessment_smoke_verifier_rejects_an_inconsistent_linear_explanation():
    """Endpoint smoke checks must detect contributions that do not reconstruct a score."""
    smoke = load_module("smoke")
    assessment = {
        "baseline": {"logit": 0, "score": 0.5, "supported": True},
        "current": {"logit": 0, "score": 0.5, "supported": True},
        "delta": {"logit": 0},
        "decomposition": {
            "reference": "training_mean",
            "units": "logit",
            "intercept": 0,
            "features": [
                {"contribution_before": 0, "contribution_after": 0, "contribution_delta": 0}
            ],
        },
    }
    smoke.verify_assessment(assessment)
    assessment["decomposition"]["features"][0]["contribution_after"] = 1
    with pytest.raises(AssertionError):
        smoke.verify_assessment(assessment)
