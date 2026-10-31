"""Recompute an exported ARIADNE certificate using the matching graph and model.

Example: python -m scripts.verify_audit certificate.json --data-dir data/processed
The certificate contains claims and evidence IDs, never executable code. A
successful witness replay proves attainability; the separate envelope
recomputation checks optimality under the stated bounded failure model.
"""

import argparse
import json
from pathlib import Path

from app.binding_audit import BindingAuditor
from app.graph_engine import GraphEngine


def verify_file(certificate_path: Path, data_dir: Path) -> dict:
    """Reject invalid files before loading the graph; report all failures explicitly."""
    try:
        if certificate_path.stat().st_size > 262_144:
            raise ValueError("Certificate exceeds the 256 KiB verification limit")
        certificate = json.loads(certificate_path.read_text(encoding="utf-8"))
        result = BindingAuditor(GraphEngine(data_dir)).verify(certificate)
    except (OSError, ValueError, RuntimeError) as error:
        result = {
            "status": "invalid",
            "valid": False,
            "checks": [],
            "errors": [str(error)],
            "verification_method": "Input validation failed before completed graph verification",
        }
    return result


def main() -> int:
    """Exit nonzero on an invalid certificate and replace any previous output report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, help="Optional JSON verification report")
    arguments = parser.parse_args()
    if arguments.output:
        inputs = [arguments.certificate] + [
            arguments.data_dir / name
            for name in ("graph.json", "model.json", "evaluation.json", "manifest.json")
        ]
        for source in inputs:
            if arguments.output.resolve() == source.resolve() or (
                arguments.output.exists() and source.exists() and arguments.output.samefile(source)
            ):
                parser.error("--output must not overwrite the input certificate or scientific data")
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text('{"status":"started","valid":false}\n', encoding="utf-8")
    report = verify_file(arguments.certificate, arguments.data_dir)
    encoded = json.dumps(report, indent=2, allow_nan=False) + "\n"
    if arguments.output:
        arguments.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
