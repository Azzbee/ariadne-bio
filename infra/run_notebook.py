"""Execute the notebook using the active interpreter in an isolated kernel spec."""

import json
import os
from pathlib import Path
import sys
import tempfile

import nbformat
from nbclient import NotebookClient


def validate_notebook_inputs(root: Path) -> None:
    """Reject mixed fits before executing or displaying historical benchmark results."""
    data = root / "data" / "processed"
    if not (data / "graph.json").is_file():
        raise RuntimeError("Graph is missing. Run make prepare-data, then make notebook.")
    required = ("model.json", "evaluation.json", "manifest.json")
    missing = [name for name in required if not (data / name).is_file()]
    if missing:
        raise RuntimeError(
            "Notebook artifacts are missing: "
            + ", ".join(missing)
            + ". Use a fresh source checkout for the saved reference, or run make notebook-refit."
        )
    model, evaluation, manifest = (
        json.loads((data / name).read_text(encoding="utf-8")) for name in required
    )
    dataset_hash = manifest.get("dataset_sha256")
    if not dataset_hash or any(
        artifact.get("dataset_sha256") != dataset_hash for artifact in (model, evaluation)
    ):
        raise RuntimeError("The notebook graph, model and evaluation use different datasets.")
    model_hash = model.get("model_sha256")
    if not model_hash or evaluation.get("model_sha256") != model_hash:
        raise RuntimeError(
            "The saved evaluation does not belong to the active model. "
            "Use a fresh source checkout for the saved reference, or run make notebook-refit."
        )
    expected = {
        "dataset_sha256": dataset_hash,
        "graph_sha256": manifest.get("graph_sha256"),
        "model_sha256": model_hash,
    }
    summaries = (
        ("reports/v1.2.0/binding-audit-summary.json", "benchmark-audits"),
        ("reports/v1.3.0/provenance-audit-summary.json", "benchmark-provenance"),
    )
    for relative, command in summaries:
        path = root / relative
        if not path.is_file():
            raise RuntimeError(f"{relative} is missing. Run make {command}, then make notebook.")
        summary = json.loads(path.read_text(encoding="utf-8"))
        if summary.get("status") != "passed" or any(
            summary.get("identity", {}).get(key) != value for key, value in expected.items()
        ):
            raise RuntimeError(
                f"{relative} is not a passing benchmark for the active graph and model. "
                f"Run make {command}, then make notebook. "
                "Fixed seeds do not guarantee identical fitted parameters across runtimes."
            )


def main() -> None:
    """Run every notebook cell and save verified outputs for inspection."""
    root = Path(__file__).resolve().parents[1]
    validate_notebook_inputs(root)
    notebook = nbformat.read(root / "demo.ipynb", as_version=4)
    with tempfile.TemporaryDirectory(prefix="ariadne-kernel-") as temporary:
        kernel = Path(temporary) / "kernels" / "ariadne"
        kernel.mkdir(parents=True)
        (kernel / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
                    "display_name": "ARIADNE verified runtime",
                    "language": "python",
                }
            ),
            encoding="utf-8",
        )
        existing = os.environ.get("JUPYTER_PATH", "")
        os.environ["JUPYTER_PATH"] = temporary + (os.pathsep + existing if existing else "")
        client = NotebookClient(
            notebook,
            timeout=300,
            kernel_name="ariadne",
            resources={"metadata": {"path": str(root)}},
        )
        client.execute()
    nbformat.write(notebook, root / "demo.executed.ipynb")
    print("Executed every cell successfully: demo.executed.ipynb")


if __name__ == "__main__":
    main()
