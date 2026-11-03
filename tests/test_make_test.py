"""Exercise the real Make dependency graph from an empty generated-data checkout."""

import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest

from scripts.export_snapshot import export_snapshot
from tests.test_graph_engine import create_fixture_engine

ROOT = Path(__file__).resolve().parents[1]

# Only expensive external commands are replaced. GNU Make executes the repository's
# unmodified targets, including recursive integration dispatch and parallel ordering.
RUNNER = r"""
import json
import os
from pathlib import Path
import sys

kind, *arguments = sys.argv[1:]
if kind == "node":
    assert arguments == ["--test", "frontend/tests/example.test.js"], arguments
    stage = "frontend"
elif arguments[:2] == ["-m", "scripts.prepare_data"]:
    stage = "prepare"
elif arguments[:2] == ["-m", "scripts.export_snapshot"]:
    stage = "snapshot"
elif arguments[:2] == ["-m", "pytest"]:
    selection = arguments[arguments.index("-m", 2) + 1]
    if selection == "integration":
        assert os.environ.get("ARIADNE_REQUIRE_NEO4J") == "1"
        stage = "integration"
    else:
        assert selection == "not integration and not llm", selection
        stage = "unit"
else:
    raise AssertionError(f"Unexpected command (refitting is forbidden): {arguments}")

with Path("steps.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps(stage) + "\n")
if os.environ.get("ARIADNE_TEST_FAIL_STAGE") == stage:
    sys.exit(23)
if stage == "prepare":
    Path("data/processed/graph.json").write_text('{"prepared":true}')
elif stage == "snapshot":
    assert Path("data/processed/graph.json").exists(), "graph was not prepared"
    Path("frontend/data").mkdir(parents=True, exist_ok=True)
    Path("frontend/data/manifest.json").write_text('{"mode":"snapshot"}')
else:
    assert Path("frontend/data/manifest.json").exists(), "snapshot missing before tests"
"""


@pytest.fixture
def make_checkout(tmp_path):
    """Run actual Make recipes with isolated recording Python/Node command drivers."""
    shutil.copyfile(ROOT / "Makefile", tmp_path / "Makefile")
    (tmp_path / "frontend/tests").mkdir(parents=True)
    (tmp_path / "frontend/tests/example.test.js").write_text("// command fixture\n")
    (tmp_path / "data/processed").mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    preserved = {
        "data/processed/model.json": b'{"model":"saved reference"}\n',
        "data/processed/evaluation.json": b'{"evaluation":"saved reference"}\n',
        "reports/reference.json": b'{"audit":"saved reference"}\n',
    }
    for relative, content in preserved.items():
        (tmp_path / relative).write_bytes(content)
    driver = tmp_path / "command_driver.py"
    driver.write_text(RUNNER, encoding="utf-8")
    tools = tmp_path / "bin"
    tools.mkdir()
    python_driver = f"{shlex.quote(sys.executable)} {shlex.quote(str(driver))}"
    node = tools / "node"
    node.write_text(f'#!/bin/sh\nexec {python_driver} node "$@"\n', encoding="utf-8")
    node.chmod(0o755)

    def run(*, integration=False, fail_stage=None):
        environment = os.environ.copy()
        # A test process must not inherit the outer Make invocation's command
        # variables or jobserver descriptors into this independent fixture.
        for name in ("MAKEFLAGS", "MFLAGS", "MAKEOVERRIDES", "ARIADNE_TEST_FAIL_STAGE"):
            environment.pop(name, None)
        environment["PATH"] = str(tools) + os.pathsep + environment["PATH"]
        if fail_stage:
            environment["ARIADNE_TEST_FAIL_STAGE"] = fail_stage
        result = subprocess.run(
            [
                "make",
                "-j4",
                "test",
                f"PYTHON={python_driver} python",
                f"INTEGRATION={int(integration)}",
            ],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
        for relative, content in preserved.items():
            assert (tmp_path / relative).read_bytes() == content
        steps = [json.loads(line) for line in (tmp_path / "steps.jsonl").read_text().splitlines()]
        return result, steps

    return run


@pytest.mark.parametrize("integration", [False, True])
def test_clean_make_test_builds_inputs_before_running_suites(make_checkout, integration):
    """Both public test commands work without a preexisting graph or browser manifest."""
    result, steps = make_checkout(integration=integration)
    assert result.returncode == 0, result.stdout + result.stderr
    assert steps[:2] == ["prepare", "snapshot"]
    assert steps[2:] == ["unit", "frontend"] + (["integration"] if integration else [])


@pytest.mark.parametrize("stage", ["prepare", "snapshot"])
def test_make_test_aborts_when_generated_inputs_fail(make_checkout, stage):
    """No unit/frontend/live-suite success can hide a failed prerequisite."""
    result, steps = make_checkout(integration=True, fail_stage=stage)
    assert result.returncode != 0
    assert steps == (["prepare"] if stage == "prepare" else ["prepare", "snapshot"])


def test_frontend_failure_still_blocks_live_integration_success(make_checkout):
    """The integration option must retain, rather than bypass, the frontend gate."""
    result, steps = make_checkout(integration=True, fail_stage="frontend")
    assert result.returncode != 0
    assert steps == ["prepare", "snapshot", "unit", "frontend"]


def test_actual_snapshot_export_preserves_saved_scientific_inputs(tmp_path):
    """Generating real verified browser cases cannot refit or rewrite retained evidence."""
    prepared = tmp_path / "prepared"
    prepared.mkdir()
    engine = create_fixture_engine(prepared)
    (prepared / "reference-audit.json").write_bytes(b'{"retained":"scientific evidence"}\n')
    before = {path.name: path.read_bytes() for path in prepared.iterdir() if path.is_file()}
    manifest = export_snapshot(engine, tmp_path / "snapshot", ["Disease::D1"], top_k=1)
    assert manifest["case_count"] == 1
    assert (tmp_path / "snapshot/manifest.json").is_file()
    assert {path.name: path.read_bytes() for path in prepared.iterdir() if path.is_file()} == before
