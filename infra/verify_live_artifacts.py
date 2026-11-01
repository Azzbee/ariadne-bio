"""Bind copied live-container model artifacts to every actual HTTP smoke certificate."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from app.binding_audit import certificate_digest

CERTIFICATES = (
    ("binding_audit", "certificate", "verification", "binding-envelope-v1"),
    ("provenance_audit", "certificate", "verification", "provenance-group-exhaustive-v1"),
    (
        "provenance_audit",
        "conditional_certificate",
        "conditional_verification",
        "provenance-group-exhaustive-v1",
    ),
    (
        "provenance_audit",
        "selected_pubmed_certificate",
        "selected_pubmed_verification",
        "provenance-group-exhaustive-v1",
    ),
)


def verify(reports: Path) -> dict:
    """Check actual parameter self-hash and all graph/model identity references."""
    names = ("live-model.json", "live-manifest.json", "live-evaluation.json", "http_smoke.json")
    files = {name: (reports / name).read_bytes() for name in names}
    model, manifest, evaluation, smoke = [json.loads(files[name]) for name in names]
    unsigned = {key: value for key, value in model.items() if key != "model_sha256"}
    actual_model = sha256(
        json.dumps(unsigned, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if model.get("model_sha256") != actual_model:
        raise ValueError("Copied live model's parameter checksum does not match")
    identity = {
        "dataset_sha256": manifest.get("dataset_sha256"),
        "graph_sha256": manifest.get("graph_sha256"),
        "model_sha256": actual_model,
    }
    if any(not isinstance(value, str) or len(value) != 64 for value in identity.values()):
        raise ValueError("Copied live manifest/model must carry complete identities")
    if model.get("dataset_sha256") != identity["dataset_sha256"]:
        raise ValueError("Copied live model and manifest disagree on dataset identity")
    if any(evaluation.get(key) != identity[key] for key in ("dataset_sha256", "model_sha256")):
        raise ValueError("Copied live evaluation does not match the exact live fitted model")
    if smoke.get("status") != "passed":
        raise ValueError("Live HTTP smoke did not pass")
    if smoke.get("assessment", {}).get("fixed_model_sha256") != actual_model:
        raise ValueError("Live assessment does not match the copied model")
    bindings = []
    for section, key, verification_key, method in CERTIFICATES:
        certificate = smoke[section][key]
        verification = smoke[section][verification_key]
        label = f"{section}.{key}"
        if certificate.get("method") != method:
            raise ValueError(f"Unexpected certificate method at {label}")
        if certificate.get("certificate_sha256") != certificate_digest(certificate):
            raise ValueError(f"Certificate checksum mismatch at {label}")
        if any(
            certificate.get("identity", {}).get(name) != value for name, value in identity.items()
        ):
            raise ValueError(f"Copied live artifacts do not match {label}")
        if verification.get("valid") is not True or verification.get("status") != "verified":
            raise ValueError(f"Missing successful live verification at {label}")
        bindings.append(
            {
                "path": label,
                "certificate_sha256": certificate["certificate_sha256"],
                "method": method,
            }
        )
    return {
        "status": "passed",
        "identity": identity,
        "certificates": bindings,
        "files": [
            {"path": name, "bytes": len(value), "sha256": sha256(value).hexdigest()}
            for name, value in files.items()
        ],
        "input_contract": (
            "CI copies live-model.json, live-manifest.json and live-evaluation.json "
            "directly from the running API container after HTTP smoke. This verifier "
            "binds their bytes/parameters to all smoke certificates; the CI copy step "
            "establishes their container origin. It does not substitute the quality-job "
            "fit or the committed research-snapshot model."
        ),
        "offline_replay": (
            "Prepare the pinned graph with scripts.prepare_data, then use these exact "
            "model.json, manifest.json and evaluation.json files for smoke-certificate "
            "replay. Do not retrain with make data before that replay."
        ),
    }


def main() -> None:
    """Remove stale output first, then write a success report only after every binding passes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    args = parser.parse_args()
    output = args.reports_dir / "live-artifacts-verification.json"
    output.unlink(missing_ok=True)
    report = verify(args.reports_dir)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    identity = report["identity"]["model_sha256"]
    print(f"Bound {len(report['certificates'])} live certificates to model {identity}")


if __name__ == "__main__":
    main()
