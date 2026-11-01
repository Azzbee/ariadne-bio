"""Downloaded certificates require genuine replay with their exact retained fit."""

from copy import deepcopy
from hashlib import sha256
import json
import sys

import pytest

from app.binding_audit import BindingAuditor, certificate_digest
from app.graph_engine import GraphEngine
from app.provenance_audit import ProvenanceAuditor
from infra import replay_ci_certificates as replay_cli
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def replay_bundle(tmp_path):
    """Small real certificates and a deliberately different adjacent graph-directory fit."""
    data = tmp_path / "data"
    data.mkdir()
    graph = tiny_graph()
    graph["metadata"]["dataset_sha256"] = "a" * 64
    for edge in graph["edges"]:
        if edge["type"] == "BINDS":
            edge["data"]["pubmed_ids"] = ["100"]
    engine = create_fixture_engine(data, graph)
    model = deepcopy(engine.model)
    model["dataset_sha256"] = "a" * 64
    model["model_sha256"] = sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    manifest = {
        "dataset_sha256": "a" * 64,
        "graph_sha256": sha256((data / "graph.json").read_bytes()).hexdigest(),
    }
    evaluation = {"dataset_sha256": "a" * 64, "model_sha256": model["model_sha256"]}
    values = {"model.json": model, "manifest.json": manifest, "evaluation.json": evaluation}
    for name, value in values.items():
        _write(data / name, value)
    engine = GraphEngine(data)
    binding = BindingAuditor(engine).audit("Disease::D1", "Compound::C2")
    auditor = ProvenanceAuditor(engine)
    source = auditor.audit("Disease::D1", "Compound::C2")
    conditional = auditor.audit(
        "Disease::D1", "Compound::C2", protected_group_ids=["source:Hand-counted fixture"]
    )
    pubmed = auditor.audit(
        "Disease::D1", "Compound::C2", group_kind="pubmed", group_ids=["pubmed:100"]
    )
    quality, integration = tmp_path / "quality", tmp_path / "integration"
    for kind, directory in (("quality", quality), ("integration", integration)):
        for key, name in replay_cli.ARTIFACT_FILES[kind].items():
            _write(
                directory / name,
                (
                    {"job": kind, "checkout_sha": "b" * 40, "run_id": "fixture-not-a-CI-run"}
                    if key == "context"
                    else values[key]
                ),
            )
    for name, method in replay_cli.QUALITY_CERTIFICATES:
        certificate = (
            binding if method == "binding-envelope-v1" else (pubmed if "pubmed" in name else source)
        )
        _write(quality / name, certificate)
    smoke = {"binding_audit": {}, "provenance_audit": {}}
    actual = (binding, source, conditional, pubmed)
    for (section, key, verification_key, _), certificate in zip(replay_cli.CERTIFICATES, actual):
        smoke[section][key] = certificate
        # Deliberately incorrect saved verdict: the command must recompute for itself.
        smoke[section][verification_key] = {"valid": False, "status": "not trusted"}
    _write(integration / "http_smoke.json", smoke)
    adjacent = deepcopy(model)
    adjacent["intercept"] = 20.0
    del adjacent["model_sha256"]
    adjacent["model_sha256"] = sha256(json.dumps(adjacent, sort_keys=True).encode()).hexdigest()
    _write(data / "model.json", adjacent)
    return {"graph": data / "graph.json", "quality": quality, "integration": integration}


@pytest.mark.parametrize("kind,count", [("quality", 6), ("integration", 4)])
def test_all_certificates_replay_without_reading_adjacent_fit_or_saved_verdict(
    replay_bundle, kind, count
):
    report = replay_cli.replay(replay_bundle[kind], replay_bundle["graph"], kind)
    assert report["valid"] is True
    assert report["status"] == "passed"
    assert len(report["certificates"]) == count
    assert all(item["verification"]["replayed_witnesses"] for item in report["certificates"])
    adjacent = json.loads((replay_bundle["graph"].parent / "model.json").read_text())
    assert report["identity"]["model_sha256"] != adjacent["model_sha256"]
    assert "does not authenticate" in report["interpretation"]


def test_rehashed_false_claim_fails_even_with_saved_success(replay_bundle):
    directory = replay_bundle["integration"]
    smoke_path = directory / "http_smoke.json"
    smoke = json.loads(smoke_path.read_text())
    certificate = smoke["provenance_audit"]["certificate"]
    certificate["baseline"]["score"] = 0.123
    certificate["certificate_sha256"] = certificate_digest(certificate)
    smoke["provenance_audit"]["verification"] = {"status": "verified", "valid": True}
    _write(smoke_path, smoke)
    report = replay_cli.replay(directory, replay_bundle["graph"], "integration")
    assert report["status"] == "failed"
    assert report["valid"] is False
    assert sum(item["verification"]["valid"] for item in report["certificates"]) == 3


def test_missing_required_quality_certificate_is_not_silently_skipped(replay_bundle):
    (replay_bundle["quality"] / replay_cli.QUALITY_CERTIFICATES[-1][0]).unlink()
    with pytest.raises(FileNotFoundError):
        replay_cli.replay(replay_bundle["quality"], replay_bundle["graph"], "quality")


def test_graph_mismatch_fails_before_replay(replay_bundle):
    with replay_bundle["graph"].open("a") as stream:
        stream.write("\n")
    with pytest.raises(ValueError, match="graph bytes do not match"):
        replay_cli.replay(replay_bundle["quality"], replay_bundle["graph"], "quality")


@pytest.mark.parametrize("resign", [False, True])
def test_corrupt_or_substituted_fitted_model_is_rejected(replay_bundle, resign):
    model_path = replay_bundle["quality"] / "data/processed/model.json"
    model = json.loads(model_path.read_text())
    model["intercept"] = 100.0
    if resign:
        del model["model_sha256"]
        model["model_sha256"] = sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    _write(model_path, model)
    with pytest.raises(ValueError, match="retained fitted model|parameter checksum"):
        replay_cli.replay(replay_bundle["quality"], replay_bundle["graph"], "quality")


def test_successful_cli_preserves_every_input_byte(replay_bundle, monkeypatch, tmp_path, capsys):
    before = {
        path: sha256(path.read_bytes()).hexdigest()
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    output = tmp_path / "replay.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--kind",
            "quality",
            "--artifact-dir",
            str(replay_bundle["quality"]),
            "--graph",
            str(replay_bundle["graph"]),
            "--output",
            str(output),
        ],
    )
    assert replay_cli.main() == 0
    assert json.loads(output.read_text())["valid"] is True
    assert json.loads(capsys.readouterr().out)["valid"] is True
    assert all(sha256(path.read_bytes()).hexdigest() == digest for path, digest in before.items())


def test_failed_cli_replaces_stale_success(replay_bundle, monkeypatch, tmp_path, capsys):
    output = tmp_path / "replay.json"
    output.write_text('{"status":"passed","valid":true}')
    (replay_bundle["integration"] / "live-model.json").unlink()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--kind",
            "integration",
            "--artifact-dir",
            str(replay_bundle["integration"]),
            "--graph",
            str(replay_bundle["graph"]),
            "--output",
            str(output),
        ],
    )
    assert replay_cli.main() == 1
    assert json.loads(output.read_text())["valid"] is False
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


@pytest.mark.parametrize("alias", ["inside", "graph", "adjacent_model", "hardlink"])
def test_cli_cannot_overwrite_or_alias_inputs(replay_bundle, monkeypatch, tmp_path, alias):
    graph = replay_bundle["graph"]
    output = {
        "inside": replay_bundle["quality"] / "new-output.json",
        "graph": graph,
        "adjacent_model": graph.parent / "model.json",
        "hardlink": tmp_path / "linked-model.json",
    }[alias]
    if alias == "hardlink":
        output.hardlink_to(replay_bundle["quality"] / "data/processed/model.json")
    original = graph.read_bytes()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--kind",
            "quality",
            "--artifact-dir",
            str(replay_bundle["quality"]),
            "--graph",
            str(graph),
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as exit_info:
        replay_cli.main()
    assert exit_info.value.code == 2
    assert graph.read_bytes() == original


def test_report_does_not_truncate_an_unrelated_hardlinked_artifact_member(
    replay_bundle, monkeypatch, tmp_path, capsys
):
    unrelated = replay_bundle["quality"] / "reports/junit.xml"
    unrelated.write_bytes(b"Preserved unrelated evidence bytes")
    output = tmp_path / "linked-report.json"
    output.hardlink_to(unrelated)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "replay",
            "--kind",
            "quality",
            "--artifact-dir",
            str(replay_bundle["quality"]),
            "--graph",
            str(replay_bundle["graph"]),
            "--output",
            str(output),
        ],
    )
    assert replay_cli.main() == 0
    assert unrelated.read_bytes() == b"Preserved unrelated evidence bytes"
    assert not output.samefile(unrelated)
    assert json.loads(capsys.readouterr().out)["valid"] is True


@pytest.mark.parametrize("kind", ["quality", "integration"])
def test_valid_source_certificate_cannot_impersonate_required_pubmed_scope(replay_bundle, kind):
    directory = replay_bundle[kind]
    if kind == "quality":
        source_path = directory / replay_cli.QUALITY_CERTIFICATES[-2][0]
        (directory / replay_cli.QUALITY_CERTIFICATES[-1][0]).write_bytes(source_path.read_bytes())
    else:
        path = directory / "http_smoke.json"
        smoke = json.loads(path.read_text())
        smoke["provenance_audit"]["selected_pubmed_certificate"] = smoke["provenance_audit"][
            "certificate"
        ]
        _write(path, smoke)
    with pytest.raises(ValueError, match="pubmed certificate has the wrong group scope"):
        replay_cli.replay(directory, replay_bundle["graph"], kind)


def test_valid_unprotected_source_cannot_impersonate_conditional_reaudit(replay_bundle):
    directory = replay_bundle["integration"]
    path = directory / "http_smoke.json"
    smoke = json.loads(path.read_text())
    smoke["provenance_audit"]["conditional_certificate"] = smoke["provenance_audit"]["certificate"]
    _write(path, smoke)
    with pytest.raises(ValueError, match="does not apply the source protection plan"):
        replay_cli.replay(directory, replay_bundle["graph"], "integration")


def test_unexpected_method_cannot_select_an_unrelated_verifier(replay_bundle):
    path = replay_bundle["quality"] / replay_cli.QUALITY_CERTIFICATES[0][0]
    certificate = json.loads(path.read_text())
    certificate["method"] = "unrecognised-method"
    certificate["certificate_sha256"] = certificate_digest(certificate)
    _write(path, certificate)
    with pytest.raises(ValueError, match="Unexpected certificate method"):
        replay_cli.replay(replay_bundle["quality"], replay_bundle["graph"], "quality")
