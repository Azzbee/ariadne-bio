"""Verify that the published edition contains every displayed evidence interaction."""

import copy
import hashlib
import json

import pytest

from app import __version__
from app.binding_audit import BindingAuditor
from scripts.export_snapshot import (
    build_case,
    case_filename,
    exclusion_combinations,
    export_snapshot,
    validate_case,
)
from tests.test_graph_engine import create_fixture_engine


def test_all_sixteen_configurations_have_canonical_keys():
    """Keys must agree with the browser's alphabetically sorted comma-separated format."""
    combinations = exclusion_combinations()
    assert len(combinations) == len(set(combinations)) == 16
    assert combinations[0] == ()
    assert all(tuple(sorted(combination)) == combination for combination in combinations)
    assert combinations[-1] == ("ASSOCIATES", "BINDS", "INTERACTS", "PARTICIPATES")


def test_each_displayed_candidate_is_inspectable_after_any_ablation(tmp_path):
    """A candidate falling outside top-k still has complete evidence in every scenario."""
    engine = create_fixture_engine(tmp_path)
    case = build_case(engine, "Disease::D1", top_k=1)
    validate_case(case)
    assert case["rankings"][""]["candidates"][0]["id"] == "Compound::C2"
    assert case["rankings"]["INTERACTS"]["candidates"][0]["id"] == "Compound::C1"
    assert len(case["evidence"]["Compound::C2"]) == 16
    assert len(case["assessments"]["Compound::C2"]) == 16
    off_shortlist = case["assessments"]["Compound::C2"]["INTERACTS"]
    assert off_shortlist["current"]["rank"] == 3
    assert off_shortlist["baseline"]["rank"] == 1
    assert case["assessments"]["Compound::C2"][""]["current"]["rank"] == 1
    assert case["evidence"]["Compound::C2"]["INTERACTS"]["counts"]["interaction"] == 0
    for key in ("BINDS", "ASSOCIATES", "ASSOCIATES,BINDS,INTERACTS,PARTICIPATES"):
        assert case["rankings"][key]["candidates"] == []
        assert case["evidence"]["Compound::C2"][key]["paths"] == []
        assert case["challenges"][key]["after"] == []
        current = case["assessments"]["Compound::C2"][key]["current"]
        assert current["supported"] is False
        assert current["rank"] is None
        assert current["score"] is not None
    assert case["coverage"]["assessment_count"] == 32


@pytest.mark.parametrize(
    "damage", ["missing_config", "missing_candidate", "wrong_count", "leaked_edge"]
)
def test_incomplete_or_inconsistent_exports_are_rejected(tmp_path, damage):
    """A build must fail rather than publish dangling or scientifically inconsistent UI data."""
    case = build_case(create_fixture_engine(tmp_path), "Disease::D1", top_k=1)
    if damage == "missing_config":
        del case["rankings"]["INTERACTS"]
    elif damage == "missing_candidate":
        del case["evidence"]["Compound::C2"]
    elif damage == "wrong_count":
        case["evidence"]["Compound::C2"][""]["counts"]["direct"] = 100
    else:
        case["evidence"]["Compound::C1"]["INTERACTS"]["edges"].append({"type": "INTERACTS"})
    with pytest.raises(ValueError):
        validate_case(case)


def test_manifest_files_have_verified_checksums_and_explicit_execution_mode(tmp_path):
    """The deployment manifest is auditable and never claims live agent/database execution."""
    engine = create_fixture_engine(tmp_path)
    output = tmp_path / "browser"
    manifest = export_snapshot(engine, output, ["Disease::D1", "Disease::D2"], top_k=2)
    assert manifest["mode"] == "snapshot"
    assert manifest["default_disease_id"] == "Disease::D1"
    assert manifest["case_count"] == manifest["file_count"] == 2
    assert manifest["health"]["agent_mode"] == "deterministic"
    assert manifest["health"]["version"] == __version__
    assert manifest["compounds"] == [
        {"id": f"Compound::C{index}", "name": f"C{index}"} for index in range(4)
    ]
    assert "No live LLM" in manifest["agent_disclosure"]
    assert manifest == json.loads((output / "manifest.json").read_text())
    for item in manifest["files"]:
        content = (output / item["path"]).read_bytes()
        assert len(content) == item["bytes"]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        validate_case(json.loads(content))


@pytest.mark.parametrize(
    "damage",
    [
        "missing_compound",
        "missing_variant",
        "wrong_compound",
        "wrong_features",
        "wrong_rank",
        "wrong_score",
        "missing_term",
        "wrong_contribution",
        "wrong_coefficient",
        "wrong_scale",
        "wrong_delta",
        "wrong_score_delta",
        "unsupported_rank",
    ],
)
def test_incomplete_or_inconsistent_score_assessments_fail_export(tmp_path, damage):
    """Frozen results must remain complete and reconstructible even for off-shortlist pairs."""
    case = build_case(create_fixture_engine(tmp_path), "Disease::D1", top_k=1)
    variants = case["assessments"]["Compound::C2"]
    target = variants["INTERACTS"]  # This compound is outside the exported top one.
    if damage == "missing_compound":
        del case["assessments"]["Compound::C2"]
    elif damage == "missing_variant":
        del variants["INTERACTS"]
    elif damage == "wrong_compound":
        target["compound"]["id"] = "Compound::C1"
    elif damage == "wrong_features":
        target["current"]["features"]["pathway"] += 1
    elif damage == "wrong_rank":
        variants[""]["current"]["rank"] += 1
    elif damage == "wrong_score":
        target["current"]["score"] = 0.999
    elif damage == "missing_term":
        target["decomposition"]["features"].pop()
    elif damage == "wrong_contribution":
        target["decomposition"]["features"][0]["contribution_after"] += 1
    elif damage == "wrong_coefficient":
        target["decomposition"]["features"][1]["coefficient"] += 1
    elif damage == "wrong_scale":
        target["decomposition"]["features"][0]["scale"] = 0
    elif damage == "wrong_delta":
        target["decomposition"]["features"][0]["contribution_delta"] += 1
    elif damage == "wrong_score_delta":
        target["delta"]["score"] += 1
    else:
        variants["BINDS"]["current"]["rank"] = 1
    with pytest.raises(ValueError):
        validate_case(case)


def test_export_does_not_change_the_trained_model(tmp_path):
    """Publishing an evidence challenge cannot retrain or mutate the fitted scorer."""
    engine = create_fixture_engine(tmp_path)
    original = copy.deepcopy(engine.model)
    export_snapshot(engine, tmp_path / "browser", ["Disease::D1"], top_k=1)
    assert engine.model == original


def test_invalid_export_selection_fails_clearly(tmp_path):
    """There are no silent empty manifests or uncapped export requests."""
    engine = create_fixture_engine(tmp_path)
    with pytest.raises(ValueError, match="At least one"):
        export_snapshot(engine, tmp_path / "browser", [])
    with pytest.raises(ValueError, match="top_k"):
        export_snapshot(engine, tmp_path / "browser", ["Disease::D1"], top_k=101)
    assert (
        case_filename({"id": "Disease::D1", "name": "A disease / ../?"})
        == "cases/a-disease-disease-d1.json"
    )


def test_recorded_audits_cover_every_inspectable_pair_and_preserve_full_graph_scope(tmp_path):
    """Even an off-shortlist selected compound has nine fully verified audit choices."""
    case = build_case(create_fixture_engine(tmp_path), "Disease::D1", top_k=1)
    expected = {f"{top_k}:{budget}" for top_k in (1, 5, 10) for budget in (0, 1, 2)}
    assert set(case["audits"]) == set(case["assessments"])
    assert case["coverage"]["audit_count"] == len(case["audits"]) * 9
    for compound_id, variants in case["audits"].items():
        assert set(variants) == expected
        for key, certificate in variants.items():
            recorded = case["audit_verifications"][compound_id][key]
            assert recorded["verification_execution"] == "recorded_at_export"
            assert recorded["certificate_sha256"] == certificate["certificate_sha256"]
            assert recorded["valid"] is True
            assert certificate["scope"]["universe"] == "all_recorded_BINDS_edges"


@pytest.mark.parametrize("damage", ["pair", "configuration", "hash", "verification", "identity"])
def test_missing_or_misbound_audits_fail_snapshot_validation(tmp_path, damage):
    """Static results cannot silently interpolate missing choices or reuse other proofs."""
    case = build_case(create_fixture_engine(tmp_path), "Disease::D1", top_k=1)
    if damage == "pair":
        del case["audits"]["Compound::C2"]
    elif damage == "configuration":
        del case["audits"]["Compound::C2"]["10:2"]
    elif damage == "hash":
        case["audits"]["Compound::C2"]["10:2"]["baseline"]["score"] = 0.5
    elif damage == "verification":
        case["audit_verifications"]["Compound::C2"]["10:2"]["certificate_sha256"] = "0" * 64
    else:
        case["audits"]["Compound::C2"]["10:2"]["compound"]["id"] = "Compound::C1"
    with pytest.raises(ValueError):
        validate_case(case)


def test_export_stops_if_an_actual_certificate_cannot_be_verified(tmp_path, monkeypatch):
    """A failed graph replay must prevent publishing a plausible-looking audit."""
    monkeypatch.setattr(BindingAuditor, "verify", lambda *_args: {"valid": False})
    with pytest.raises(ValueError, match="failed independent witness replay"):
        build_case(create_fixture_engine(tmp_path), "Disease::D1")


def test_failed_generation_preserves_every_previous_snapshot_byte(tmp_path):
    """A late case failure cannot combine a stale manifest with newly overwritten cases."""
    engine = create_fixture_engine(tmp_path)
    output = tmp_path / "browser"
    export_snapshot(engine, output, ["Disease::D1", "Disease::D2"], top_k=1)
    before = {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    }
    with pytest.raises(KeyError):
        export_snapshot(engine, output, ["Disease::D1", "Disease::missing"], top_k=2)
    after = {
        path.relative_to(output): path.read_bytes() for path in output.rglob("*") if path.is_file()
    }
    assert before == after


def test_failed_directory_publication_restores_the_previous_generation(tmp_path, monkeypatch):
    """A rename failure after moving the old directory rolls back before propagating."""
    from pathlib import Path  # Keep the monkeypatch local to this filesystem test.

    engine = create_fixture_engine(tmp_path)
    output = tmp_path / "browser"
    export_snapshot(engine, output, ["Disease::D1"], top_k=1)
    before = (output / "manifest.json").read_bytes()
    original = Path.rename

    def fail_new_snapshot(self, target):
        if self.name == "snapshot":
            raise OSError("simulated publication failure")
        return original(self, target)

    monkeypatch.setattr(Path, "rename", fail_new_snapshot)
    with pytest.raises(OSError, match="publication failure"):
        export_snapshot(engine, output, ["Disease::D2"], top_k=1)
    assert (output / "manifest.json").read_bytes() == before


def test_snapshot_cannot_replace_scientific_inputs_or_unrelated_files(tmp_path):
    """The generated-directory contract does not authorize replacing arbitrary folders."""
    engine = create_fixture_engine(tmp_path)
    original = (tmp_path / "graph.json").read_bytes()
    with pytest.raises(ValueError, match="source data"):
        export_snapshot(engine, tmp_path, ["Disease::D1"])
    assert (tmp_path / "graph.json").read_bytes() == original
    output = tmp_path / "browser"
    export_snapshot(engine, output, ["Disease::D1"])
    note = output / "personal-notes.txt"
    note.write_text("keep me")
    with pytest.raises(ValueError, match="unrecognized files"):
        export_snapshot(engine, output, ["Disease::D2"])
    assert note.read_text() == "keep me"
