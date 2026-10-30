"""Verify that the published edition contains every displayed evidence interaction."""

import copy
import hashlib
import json

import pytest

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
    assert case["evidence"]["Compound::C2"]["INTERACTS"]["counts"]["interaction"] == 0
    for key in ("BINDS", "ASSOCIATES", "ASSOCIATES,BINDS,INTERACTS,PARTICIPATES"):
        assert case["rankings"][key]["candidates"] == []
        assert case["evidence"]["Compound::C2"][key]["paths"] == []
        assert case["challenges"][key]["after"] == []


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
    assert "No live LLM" in manifest["agent_disclosure"]
    assert manifest == json.loads((output / "manifest.json").read_text())
    for item in manifest["files"]:
        content = (output / item["path"]).read_bytes()
        assert len(content) == item["bytes"]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        validate_case(json.loads(content))


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
