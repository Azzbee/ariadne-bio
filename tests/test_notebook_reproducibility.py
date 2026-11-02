"""Keep notebook predictions and displayed benchmark evidence on the same fit."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from infra.run_notebook import validate_notebook_inputs

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def notebook_inputs(tmp_path):
    """Create a small complete artifact bundle without loading a scientific graph."""
    identity = {
        "dataset_sha256": "dataset-a",
        "graph_sha256": "graph-a",
        "model_sha256": "model-a",
    }
    files = {
        "data/processed/graph.json": {},
        "data/processed/manifest.json": identity,
        "data/processed/model.json": identity,
        "data/processed/evaluation.json": identity,
        "reports/v1.2.0/binding-audit-summary.json": {
            "status": "passed",
            "identity": identity,
        },
        "reports/v1.3.0/provenance-audit-summary.json": {
            "status": "passed",
            "identity": identity,
        },
    }
    for relative, value in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding="utf-8")
    return tmp_path


def test_matching_reference_inputs_are_read_without_replacing_any_artifact(notebook_inputs):
    """The reference route must not refit or rewrite evidence just to validate it."""
    files = list(notebook_inputs.rglob("*.json"))
    before = {path: path.read_bytes() for path in files}
    validate_notebook_inputs(notebook_inputs)
    assert before == {path: path.read_bytes() for path in files}


def test_same_dataset_does_not_make_evaluation_from_another_fit_valid(notebook_inputs):
    """A new fit can use exactly the same graph while having different parameters."""
    path = notebook_inputs / "data/processed/evaluation.json"
    evaluation = json.loads(path.read_text())
    evaluation["model_sha256"] = "another-fit"
    path.write_text(json.dumps(evaluation))
    with pytest.raises(RuntimeError, match="evaluation does not belong to the active model"):
        validate_notebook_inputs(notebook_inputs)


def test_evaluation_from_a_different_dataset_is_rejected(notebook_inputs):
    """Matching model labels cannot hide a mismatched evaluation source."""
    path = notebook_inputs / "data/processed/evaluation.json"
    evaluation = json.loads(path.read_text())
    evaluation["dataset_sha256"] = "another-dataset"
    path.write_text(json.dumps(evaluation))
    with pytest.raises(RuntimeError, match="different datasets"):
        validate_notebook_inputs(notebook_inputs)


@pytest.mark.parametrize(
    "relative,command",
    [
        ("reports/v1.2.0/binding-audit-summary.json", "benchmark-audits"),
        ("reports/v1.3.0/provenance-audit-summary.json", "benchmark-provenance"),
    ],
)
def test_refit_requires_each_benchmark_to_match_the_new_model(notebook_inputs, relative, command):
    """A retained old summary cannot be silently displayed after a successful refit."""
    path = notebook_inputs / relative
    summary = json.loads(path.read_text())
    summary["identity"]["model_sha256"] = "old-fit"
    path.write_text(json.dumps(summary))
    with pytest.raises(RuntimeError, match=f"Run make {command}"):
        validate_notebook_inputs(notebook_inputs)


def test_missing_benchmark_cannot_be_reported_as_a_complete_notebook(notebook_inputs):
    """The complete runner must fail rather than omit an entire benchmark section."""
    (notebook_inputs / "reports/v1.3.0/provenance-audit-summary.json").unlink()
    with pytest.raises(RuntimeError, match="is missing. Run make benchmark-provenance"):
        validate_notebook_inputs(notebook_inputs)


@pytest.fixture
def recorded_make(tmp_path):
    """Run the real Makefile with observable command boundaries and injected failures."""
    shutil.copyfile(ROOT / "Makefile", tmp_path / "Makefile")
    runner = tmp_path / "python-recorder"
    runner.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        "with open(os.environ['NOTEBOOK_COMMAND_LOG'], 'a', encoding='utf-8') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "if os.environ.get('NOTEBOOK_FAILED_STEP') in sys.argv[1:]:\n"
        "    sys.exit(2)\n",
        encoding="utf-8",
    )
    runner.chmod(0o755)
    log = tmp_path / "commands.jsonl"

    def run(target, failed_step=""):
        environment = dict(
            os.environ,
            NOTEBOOK_COMMAND_LOG=str(log),
            NOTEBOOK_FAILED_STEP=failed_step,
        )
        result = subprocess.run(
            ["make", "-j4", target, f"PYTHON={runner}"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        commands = [json.loads(line) for line in log.read_text().splitlines()]
        return result, commands

    return run


def test_reference_notebook_never_refits_or_replaces_benchmarks(recorded_make):
    """The normal notebook command only executes the already matched artifacts."""
    result, commands = recorded_make("notebook")
    assert result.returncode == 0, result.stderr
    assert commands == [["infra/run_notebook.py"]]


def test_refit_finishes_both_benchmarks_before_execution_even_with_parallel_make(recorded_make):
    """A parallel make invocation must not race the new model and its audit reports."""
    result, commands = recorded_make("notebook-refit")
    assert result.returncode == 0, result.stderr
    assert commands[:2] == [["-m", "scripts.prepare_data"], ["-m", "scripts.evaluate"]]
    assert {command[1] for command in commands[2:4]} == {
        "scripts.benchmark_audits",
        "scripts.benchmark_provenance",
    }
    assert commands[4:] == [["infra/run_notebook.py"]]


def test_failed_refit_benchmark_prevents_notebook_execution(recorded_make):
    """A failed refresh cannot fall through to historical notebook output."""
    result, commands = recorded_make("notebook-refit", "scripts.benchmark_provenance")
    assert result.returncode != 0
    assert ["infra/run_notebook.py"] not in commands
