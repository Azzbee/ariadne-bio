"""Strictly replay downloaded CI certificates with their retained fitted model.

This command reads an extracted quality-evidence, integration-evidence or
mixed-evidence artifact and a separately prepared graph.json. It never trains a model, writes
into the artifact, or substitutes the committed research-snapshot model.
"""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import re
import sys
from tempfile import NamedTemporaryFile, TemporaryDirectory
import time

import numpy as np
import scipy

from app.binding_audit import BindingAuditor
from app.graph_engine import GraphEngine
from app.mixed_audit import METHOD as MIXED_METHOD, MixedAuditor
from app.provenance_audit import ProvenanceAuditor
from infra.verify_live_artifacts import CERTIFICATES

QUALITY_CERTIFICATES = (
    ("reports/v1.2.0/binding-audit-example-competitor.json", "binding-envelope-v1"),
    ("reports/v1.2.0/binding-audit-example-greedy.json", "binding-envelope-v1"),
    ("reports/v1.2.0/binding-audit-example-strong-greedy.json", "binding-envelope-v1"),
    ("reports/v1.2.0/binding-audit-example-scope.json", "binding-envelope-v1"),
    ("reports/v1.3.0/provenance-audit-example-source.json", "provenance-group-exhaustive-v1"),
    ("reports/v1.3.0/provenance-audit-example-pubmed.json", "provenance-group-exhaustive-v1"),
)
MIXED_CERTIFICATES = (
    ("reports/v1.4.0/mixed-audit-example-first.json", MIXED_METHOD),
    ("reports/v1.4.0/mixed-audit-example-last.json", MIXED_METHOD),
)
ARTIFACT_FILES = {
    "mixed": {
        "model.json": "data/processed/model.json",
        "manifest.json": "data/processed/manifest.json",
        "evaluation.json": "data/processed/evaluation.json",
        "context": "reports/ci-mixed.json",
    },
    "quality": {
        "model.json": "data/processed/model.json",
        "manifest.json": "data/processed/manifest.json",
        "evaluation.json": "data/processed/evaluation.json",
        "context": "reports/ci-quality.json",
    },
    "integration": {
        "model.json": "live-model.json",
        "manifest.json": "live-manifest.json",
        "evaluation.json": "live-evaluation.json",
        "context": "ci-integration.json",
    },
}


def _identity(values: dict, graph_bytes: bytes) -> dict:
    """Require actual self-hashed parameters and one exact graph/dataset identity."""
    model, manifest, evaluation = (
        values[name] for name in ("model.json", "manifest.json", "evaluation.json")
    )
    unsigned = {key: value for key, value in model.items() if key != "model_sha256"}
    actual_model = sha256(
        json.dumps(unsigned, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()
    if model.get("model_sha256") != actual_model:
        raise ValueError("Retained model parameter checksum mismatch")
    identity = {
        "dataset_sha256": manifest.get("dataset_sha256"),
        "graph_sha256": sha256(graph_bytes).hexdigest(),
        "model_sha256": actual_model,
    }
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in identity.values()
    ):
        raise ValueError("Retained artifacts require complete SHA-256 identities")
    if manifest.get("graph_sha256") != identity["graph_sha256"]:
        raise ValueError("Prepared graph bytes do not match the retained CI manifest")
    if model.get("dataset_sha256") != identity["dataset_sha256"]:
        raise ValueError("Retained model and manifest have different dataset identities")
    if any(evaluation.get(key) != identity[key] for key in ("dataset_sha256", "model_sha256")):
        raise ValueError("Retained evaluation does not identify the retained fitted model")
    return identity


def _check_roles(certificates: list, kind: str) -> None:
    """Require actual source, citation and conditional coverage in their named slots."""
    by_path = {path: certificate for path, _, certificate in certificates}
    if kind == "mixed":
        for _, _, certificate in certificates:
            if (
                certificate.get("scope", {}).get("group_kind") != "source"
                or not certificate.get("scope", {}).get("group_ids")
                or (certificate.get("group_budget"), certificate.get("edge_budget")) != (1, 1)
                or certificate.get("top_k") != 10
            ):
                raise ValueError("Required joint certificate has the wrong group or budget scope")
        return
    if kind == "quality":
        source = by_path[QUALITY_CERTIFICATES[-2][0]]
        pubmed = by_path[QUALITY_CERTIFICATES[-1][0]]
    else:
        source = by_path["http_smoke.json:provenance_audit.certificate"]
        pubmed = by_path["http_smoke.json:provenance_audit.selected_pubmed_certificate"]
    for expected, certificate in (("source", source), ("pubmed", pubmed)):
        scope = certificate.get("scope", {})
        if scope.get("group_kind") != expected or not scope.get("group_ids"):
            raise ValueError(f"Required {expected} certificate has the wrong group scope")
        if scope.get("protected_group_ids") != []:
            raise ValueError(f"Required baseline {expected} certificate must be unprotected")
    if kind == "integration":
        conditional = by_path["http_smoke.json:provenance_audit.conditional_certificate"]
        scope = conditional.get("scope", {})
        plan = source.get("protection_plan", {})
        if (
            scope.get("group_kind") != "source"
            or scope.get("group_ids") != source["scope"]["group_ids"]
            or scope.get("protected_group_ids") != plan.get("representative")
            or plan.get("status") not in {"optimal", "already_robust"}
            or any(
                conditional.get(key) != source.get(key)
                for key in ("disease", "compound", "top_k", "budget", "identity")
            )
            or conditional.get("protection_plan", {}).get("status") != "already_robust"
        ):
            raise ValueError("Conditional certificate does not apply the source protection plan")
        binding = by_path["http_smoke.json:binding_audit.certificate"]
        if any(
            certificate.get(key) != source.get(key)
            for certificate in (binding, pubmed, by_path["http_smoke.json:mixed_audit.certificate"])
            for key in ("disease", "compound")
        ):
            raise ValueError("Live certificate roles do not describe the same selected pair")


def replay(artifact_dir: Path, graph_path: Path, kind: str) -> dict:
    """Recompute every required example or live certificate; do not trust saved verdicts."""
    if kind not in ARTIFACT_FILES:
        raise ValueError("Artifact kind must be quality, integration or mixed")
    started = time.perf_counter()
    files = {}

    def read(name):
        raw = (artifact_dir / name).read_bytes()
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"Expected a JSON object in {name}")
        files[name] = {"path": name, "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
        return raw, value

    raw_inputs, values = {}, {}
    for key, name in ARTIFACT_FILES[kind].items():
        raw_inputs[key], values[key] = read(name)
    if values["context"].get("job") != kind:
        raise ValueError("Artifact job context does not match the requested kind")
    graph_bytes = graph_path.read_bytes()
    identity = _identity(values, graph_bytes)
    certificates = []
    if kind in {"quality", "mixed"}:
        for name, method in (QUALITY_CERTIFICATES if kind == "quality" else MIXED_CERTIFICATES):
            _, certificate = read(name)
            certificates.append((name, method, certificate))
    else:
        _, smoke = read("http_smoke.json")
        for section, key, _, method in CERTIFICATES:
            certificate = smoke.get(section, {}).get(key)
            if not isinstance(certificate, dict):
                raise ValueError(f"Missing complete live certificate: {section}.{key}")
            certificates.append((f"http_smoke.json:{section}.{key}", method, certificate))
    _check_roles(certificates, kind)

    results = []
    with TemporaryDirectory(prefix="ariadne-ci-replay-") as temporary:
        data_dir = Path(temporary)
        (data_dir / "graph.json").write_bytes(graph_bytes)
        for name in ("model.json", "manifest.json", "evaluation.json"):
            (data_dir / name).write_bytes(raw_inputs[name])
        engine = GraphEngine(data_dir)
        auditors = {}
        if kind == "mixed":
            auditor = MixedAuditor(engine)
            auditors[MIXED_METHOD] = auditor
            supported_diseases = [
                disease
                for disease in engine.entities["Disease"]
                if engine.rankings(disease, limit=1)["candidates"]
            ]
            if not supported_diseases:
                raise ValueError("Mixed evidence requires a nonempty canonical cohort")
            expected = (
                (supported_diseases[0], auditor.baseline_candidates(supported_diseases[0], 10)[0]),
                (
                    supported_diseases[-1],
                    auditor.baseline_candidates(supported_diseases[-1], 10)[-1],
                ),
            )
            for (_, _, certificate), (disease, candidate) in zip(certificates, expected):
                canonical = auditor.audit(disease, candidate["id"], top_k=10)
                if certificate.get("certificate_sha256") != canonical["certificate_sha256"]:
                    raise ValueError(
                        "Mixed example does not match its complete canonical cohort role"
                    )
        for location, method, certificate in certificates:
            if certificate.get("method") != method:
                raise ValueError(f"Unexpected certificate method at {location}")
            if any(
                certificate.get("identity", {}).get(key) != value for key, value in identity.items()
            ):
                raise ValueError(f"Certificate input identity mismatch at {location}")
            if method not in auditors:
                auditor_type = {
                    "binding-envelope-v1": BindingAuditor,
                    "provenance-group-exhaustive-v1": ProvenanceAuditor,
                    MIXED_METHOD: MixedAuditor,
                }[method]
                auditors[method] = auditor_type(engine)
            verification = auditors[method].verify(certificate)
            results.append(
                {
                    "path": location,
                    "method": method,
                    "scorer": certificate.get("identity", {}).get("scorer"),
                    "certificate_sha256": certificate.get("certificate_sha256"),
                    "verification": verification,
                }
            )
    valid = all(item["verification"].get("valid") is True for item in results)
    context_keys = ("checkout_sha", "repository", "run_id", "run_attempt", "job", "event")
    return {
        "status": "passed" if valid else "failed",
        "valid": valid,
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.perf_counter() - started,
        "artifact_kind": kind,
        "artifact_context": {key: values["context"].get(key) for key in context_keys},
        "identity": identity,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "numpy": np.__version__,
            "scipy": scipy.__version__,
        },
        "graph": {"bytes": len(graph_bytes), "sha256": identity["graph_sha256"]},
        "files": sorted(files.values(), key=lambda item: item["path"]),
        "certificates": results,
        "interpretation": (
            "Actual local recomputation and independent matrix-witness replay with the exact "
            "retained model and graph; no saved verification verdict is trusted. This does not "
            "authenticate the artifact's origin or establish that its GitHub workflow passed. "
            "Check download hashes, checkout identity and actual CI conclusions separately."
        ),
    }


def _write_report(path: Path, encoded: str) -> None:
    """Replace the report inode atomically so unrelated hardlinked inputs stay intact."""
    temporary_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}-", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(encoded)
        os.replace(temporary_path, path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)


def main() -> int:
    """Write a fresh verdict, return nonzero on any mismatch, and protect all inputs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--graph", type=Path, default=Path("data/processed/graph.json"))
    parser.add_argument("--kind", choices=tuple(ARTIFACT_FILES), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        if args.output.resolve().is_relative_to(args.artifact_dir.resolve()):
            parser.error("--output must be outside the extracted artifact directory")
        if args.output.resolve().is_relative_to(args.graph.parent.resolve()):
            parser.error("--output must be outside the prepared graph directory")
        names = list(ARTIFACT_FILES[args.kind].values())
        if args.kind == "quality":
            names.extend(name for name, _ in QUALITY_CERTIFICATES)
        elif args.kind == "mixed":
            names.extend(name for name, _ in MIXED_CERTIFICATES)
        else:
            names.append("http_smoke.json")
        inputs = [args.graph] + [args.artifact_dir / name for name in names]
        if any(
            args.output.resolve() == source.resolve()
            or (args.output.exists() and source.exists() and args.output.samefile(source))
            for source in inputs
        ):
            parser.error("--output must not overwrite or alias any replay input")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        _write_report(args.output, '{"status":"started","valid":false}\n')
    try:
        report = replay(args.artifact_dir, args.graph, args.kind)
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        report = {"status": "failed", "valid": False, "errors": [str(error)]}
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    if args.output:
        _write_report(args.output, encoded)
    print(encoded, end="")
    return 0 if report["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
