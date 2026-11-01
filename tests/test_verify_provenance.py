"""Both finite audit methods work through the same offline certificate verifier."""

import json
import subprocess
import sys

from app.binding_audit import certificate_digest
from app.provenance_audit import ProvenanceAuditor
from scripts.verify_audit import verify_file
from tests.test_provenance_api import provenance_fixture


def test_cli_dispatches_and_replays_correlated_withdrawals(tmp_path):
    """The exported object alone chooses a supported bounded verifier, never executable code."""
    engine = provenance_fixture(tmp_path)
    certificate = ProvenanceAuditor(engine).audit("Disease::D1", "Compound::C2")
    source = tmp_path / "provenance-certificate.json"
    source.write_text(json.dumps(certificate), encoding="utf-8")
    assert verify_file(source, tmp_path)["valid"] is True
    destination = tmp_path / "verification.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.verify_audit",
            str(source),
            "--data-dir",
            str(tmp_path),
            "--output",
            str(destination),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["valid"] is True
    assert json.loads(destination.read_text())["valid"] is True

    certificate["results"][-1]["robust"] = True
    certificate["certificate_sha256"] = certificate_digest(certificate)
    source.write_text(json.dumps(certificate), encoding="utf-8")
    invalid = subprocess.run(result.args, text=True, capture_output=True, check=False)
    assert invalid.returncode == 1
    assert json.loads(destination.read_text())["valid"] is False


def test_unknown_method_cannot_borrow_provenance_verification(tmp_path):
    """Recognized certificate types have separate exact meanings."""
    engine = provenance_fixture(tmp_path)
    certificate = ProvenanceAuditor(engine).audit("Disease::D1", "Compound::C2")
    certificate["method"] = "arbitrary-code"
    certificate["certificate_sha256"] = certificate_digest(certificate)
    source = tmp_path / "wrong-method.json"
    source.write_text(json.dumps(certificate), encoding="utf-8")
    assert verify_file(source, tmp_path)["valid"] is False
