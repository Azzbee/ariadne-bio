"""An offline certificate is useful only when independent users can replay it."""

import json

import pytest

from app.binding_audit import BindingAuditor, certificate_digest
from scripts import verify_audit
from tests.test_graph_engine import create_fixture_engine


def test_offline_verifier_accepts_matching_inputs_and_rejects_rehashed_forgery(tmp_path):
    """Recalculating a checksum cannot turn a false mathematical claim into a valid one."""
    auditor = BindingAuditor(create_fixture_engine(tmp_path))
    certificate = auditor.audit("Disease::D1", "Compound::C2", top_k=1)
    path = tmp_path / "certificate.json"
    path.write_text(json.dumps(certificate))
    assert verify_audit.verify_file(path, tmp_path)["valid"] is True
    certificate["results"][0]["worst_supported_rank"] = 1000
    certificate["certificate_sha256"] = certificate_digest(certificate)
    path.write_text(json.dumps(certificate))
    report = verify_audit.verify_file(path, tmp_path)
    assert report["valid"] is False
    assert "recomputed" in report["errors"][0]


@pytest.mark.parametrize("content", ["not json", "null", "[]", '{"x": NaN}', "x" * 262_145])
def test_bad_files_are_explicitly_invalid(tmp_path, content):
    """Bad JSON, nonobjects, nonfinite numbers and excessive bytes never yield success."""
    create_fixture_engine(tmp_path)
    path = tmp_path / "certificate.json"
    path.write_text(content)
    report = verify_audit.verify_file(path, tmp_path)
    assert report["status"] == "invalid"
    assert report["errors"]


def test_cli_returns_failure_and_overwrites_a_stale_success(tmp_path, monkeypatch, capsys):
    """Interrupted or invalid verification cannot leave a previous successful report."""
    path = tmp_path / "missing.json"
    output = tmp_path / "verification.json"
    output.write_text('{"valid":true}')
    monkeypatch.setattr(
        "sys.argv",
        ["verify_audit", str(path), "--data-dir", str(tmp_path), "--output", str(output)],
    )
    assert verify_audit.main() == 1
    assert json.loads(output.read_text())["valid"] is False
    assert json.loads(capsys.readouterr().out)["valid"] is False


def test_cli_success_can_be_used_in_automated_review(tmp_path, monkeypatch, capsys):
    """The successful process contract includes a zero exit code and a JSON report."""
    auditor = BindingAuditor(create_fixture_engine(tmp_path))
    path = tmp_path / "certificate.json"
    path.write_text(json.dumps(auditor.audit("Disease::D1", "Compound::C2")))
    monkeypatch.setattr("sys.argv", ["verify_audit", str(path), "--data-dir", str(tmp_path)])
    assert verify_audit.main() == 0
    assert json.loads(capsys.readouterr().out)["status"] == "verified"


def test_cli_will_not_overwrite_its_input_certificate(tmp_path, monkeypatch):
    """A mistaken output filename must preserve the input evidence artifact."""
    path = tmp_path / "certificate.json"
    original = '{"preserve":"input"}'
    path.write_text(original)
    monkeypatch.setattr("sys.argv", ["verify_audit", str(path), "--output", str(path)])
    with pytest.raises(SystemExit):
        verify_audit.main()
    assert path.read_text() == original


@pytest.mark.parametrize("link", ["same_path", "symlink", "hardlink"])
def test_cli_protects_scientific_inputs_even_through_aliases(tmp_path, monkeypatch, link):
    """Reporting must never overwrite the fitted model before verification can read it."""
    engine = create_fixture_engine(tmp_path)
    certificate = tmp_path / "certificate.json"
    certificate.write_text(json.dumps(BindingAuditor(engine).audit("Disease::D1", "Compound::C2")))
    model = tmp_path / "model.json"
    original = model.read_bytes()
    output = model if link == "same_path" else tmp_path / "alias.json"
    if link == "symlink":
        output.symlink_to(model)
    elif link == "hardlink":
        output.hardlink_to(model)
    monkeypatch.setattr(
        "sys.argv",
        ["verify_audit", str(certificate), "--data-dir", str(tmp_path), "--output", str(output)],
    )
    with pytest.raises(SystemExit):
        verify_audit.main()
    assert model.read_bytes() == original
