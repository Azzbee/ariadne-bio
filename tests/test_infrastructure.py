"""Security and lifecycle tests for first-run setup and stack configuration."""

import importlib.util
from pathlib import Path
import stat
import subprocess

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
