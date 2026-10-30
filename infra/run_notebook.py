"""Execute the notebook using the active interpreter in an isolated kernel spec."""

import json
import os
from pathlib import Path
import sys
import tempfile

import nbformat
from nbclient import NotebookClient


def main() -> None:
    """Run every notebook cell and save verified outputs for inspection."""
    root = Path(__file__).resolve().parents[1]
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
