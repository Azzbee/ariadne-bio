"""Live-container replay artifacts must match every retained HTTP certificate."""

from copy import deepcopy
from hashlib import sha256
import json

import pytest

from app.binding_audit import certificate_digest
from infra import verify_live_artifacts


@pytest.fixture
def live_files(tmp_path):
    """An explicit identity-only fixture, never represented as a real container run."""
    model = {"name": "Identity fixture", "dataset_sha256": "a" * 64, "coefficients": [1.0]}
    model_hash = sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    model["model_sha256"] = model_hash
    manifest = {"dataset_sha256": "a" * 64, "graph_sha256": "b" * 64}
    evaluation = {"dataset_sha256": "a" * 64, "model_sha256": model_hash}
    identity = {**manifest, "model_sha256": model_hash}
    smoke = {
        "status": "passed",
        "assessment": {"fixed_model_sha256": model_hash},
        "binding_audit": {},
        "provenance_audit": {},
    }
    for section, key, verification_key, method in verify_live_artifacts.CERTIFICATES:
        certificate = {"method": method, "identity": deepcopy(identity), "fixture": key}
        certificate["certificate_sha256"] = certificate_digest(certificate)
        smoke[section][key] = certificate
        smoke[section][verification_key] = {"status": "verified", "valid": True}
    values = {
        "live-model.json": model,
        "live-manifest.json": manifest,
        "live-evaluation.json": evaluation,
        "http_smoke.json": smoke,
    }
    for name, value in values.items():
        (tmp_path / name).write_text(json.dumps(value))
    return tmp_path, values


def rewrite(directory, values):
    """Commit intentional fixture corruption to its actual input file."""
    for name, value in values.items():
        (directory / name).write_text(json.dumps(value))


def test_all_four_certificate_bytes_are_bound_to_actual_model_parameters(live_files):
    """Each audit variant must use the exact copied model and graph identity."""
    directory, _ = live_files
    report = verify_live_artifacts.verify(directory)
    assert report["status"] == "passed"
    assert len(report["certificates"]) == 4
    for item in report["files"]:
        assert sha256((directory / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    assert "quality-job" in report["input_contract"]


@pytest.mark.parametrize("position", range(4))
def test_one_mismatched_rehashed_certificate_fails_the_entire_binding(live_files, position):
    """A valid content hash cannot hide a certificate from a different fitted model."""
    directory, values = live_files
    section, key, _, _ = verify_live_artifacts.CERTIFICATES[position]
    certificate = values["http_smoke.json"][section][key]
    certificate["identity"]["model_sha256"] = "f" * 64
    certificate["certificate_sha256"] = certificate_digest(certificate)
    rewrite(directory, values)
    with pytest.raises(ValueError, match="do not match"):
        verify_live_artifacts.verify(directory)


@pytest.mark.parametrize(
    "filename, key, value, message",
    [
        ("live-model.json", "coefficients", [2.0], "parameter checksum"),
        ("live-evaluation.json", "model_sha256", "f" * 64, "evaluation does not match"),
        ("live-manifest.json", "graph_sha256", "f" * 64, "do not match"),
        ("http_smoke.json", "status", "failed", "smoke did not pass"),
    ],
)
def test_mixed_or_modified_replay_inputs_fail_closed(live_files, filename, key, value, message):
    """Separate quality/snapshot artifacts cannot silently substitute for the live fit."""
    directory, values = live_files
    values[filename][key] = value
    rewrite(directory, values)
    with pytest.raises(ValueError, match=message):
        verify_live_artifacts.verify(directory)


def test_cli_invalidates_stale_success_before_verification_failure(live_files, monkeypatch):
    """A failed later invocation cannot leave a previous green report behind."""
    directory, _ = live_files
    output = directory / "live-artifacts-verification.json"
    output.write_text('{"status":"old success"}')
    (directory / "live-model.json").unlink()
    monkeypatch.setattr("sys.argv", ["verify_live_artifacts", "--reports-dir", str(directory)])
    with pytest.raises(FileNotFoundError):
        verify_live_artifacts.main()
    assert not output.exists()
