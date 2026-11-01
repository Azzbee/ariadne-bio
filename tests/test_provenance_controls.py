"""Independent path and sampling accounting for descriptive size controls."""

import json

import numpy as np
import pytest

from app.binding_audit import certificate_digest
from scripts import provenance_controls
from tests.test_binding_audit import _oracle
from tests.test_graph_engine import create_fixture_engine, tiny_graph


def test_every_seeded_draw_has_exact_size_and_matches_literal_path_oracle(tmp_path):
    graph = tiny_graph()
    graph["edges"][0]["sources"] = ["single"]
    engine = create_fixture_engine(tmp_path, graph)
    result = provenance_controls.simulate_case(
        engine, "Disease::D1", "Compound::C1", "source:single", draws=40, seed=71
    )
    records = sorted(edge["id"] for edge in graph["edges"] if edge["type"] == "BINDS")
    rng = np.random.Generator(np.random.PCG64(71))
    missing = 0
    for sample in result["samples"]:
        chosen = np.sort(rng.choice(len(records), size=1, replace=False))
        removed = [records[index] for index in chosen]
        expected = _oracle(graph, engine.model, "Disease::D1", removed)["Compound::C1"]
        assert {key: sample[key] for key in expected} == expected
        assert sample["removed_edge_count"] == len(set(removed)) == 1
        assert sample["removed_edge_ids_sha256"] == certificate_digest({"value": removed})
        missing += not expected["supported"]
    assert result["summary"]["unsupported_draws"] == missing
    assert result["summary"]["at_least_as_adverse_as_group_draws"] == missing
    assert result["summary"]["top_ten_failure_draws"] == missing
    assert result["verification"]["matrix_replay_checks"] >= 2
    assert (
        provenance_controls.simulate_case(
            engine, "Disease::D1", "Compound::C1", "source:single", draws=40, seed=71
        )
        == result
    )


def test_full_universe_withdrawal_keeps_unsupported_separate_from_ranks(tmp_path):
    engine = create_fixture_engine(tmp_path)
    result = provenance_controls.simulate_case(
        engine, "Disease::D1", "Compound::C1", "source:Hand-counted fixture", draws=3, seed=0
    )
    assert result["scope"]["removed_edges_per_draw"] == 3
    assert result["summary"]["supported_draws"] == 0
    assert result["summary"]["supported_rank_quantiles"] is None
    assert result["summary"]["at_least_as_adverse_as_group_draws"] == 3
    assert all(sample["rank"] is None for sample in result["samples"])
    assert len({sample["removed_edge_ids_sha256"] for sample in result["samples"]}) == 1


@pytest.mark.parametrize(
    "setting",
    [{"draws": 0}, {"draws": True}, {"draws": 1.5}, {"seed": -1}, {"seed": False}, {"seed": "42"}],
)
def test_invalid_simulation_parameters_rejected(tmp_path, setting):
    with pytest.raises(ValueError):
        provenance_controls.simulate_case(
            create_fixture_engine(tmp_path),
            "Disease::D1",
            "Compound::C1",
            "source:Hand-counted fixture",
            **setting,
        )


def test_fixed_examples_fail_explicitly_when_dataset_is_not_available(tmp_path):
    with pytest.raises(ValueError, match="full dataset"):
        provenance_controls.run_controls(create_fixture_engine(tmp_path), draws=1)


def test_failed_controls_replace_stale_success(tmp_path):
    create_fixture_engine(tmp_path)
    output = tmp_path / "controls.json"
    output.write_text('{"status":"passed"}')
    with pytest.raises(ValueError, match="full dataset"):
        provenance_controls.main(["--data-dir", str(tmp_path), "--output", str(output)])
    assert json.loads(output.read_text())["status"] == "failed"


@pytest.mark.parametrize("alias", ["direct", "symlink", "hardlink"])
def test_controls_cannot_overwrite_dataset_inputs(tmp_path, alias):
    create_fixture_engine(tmp_path)
    original = tmp_path / "graph.json"
    before = original.read_bytes()
    output = tmp_path / "controls.json"
    if alias == "direct":
        output = original
    elif alias == "symlink":
        output.symlink_to(original)
    else:
        output.hardlink_to(original)
    with pytest.raises(ValueError, match="inputs"):
        provenance_controls.main(["--data-dir", str(tmp_path), "--output", str(output)])
    assert original.read_bytes() == before


def test_false_group_verification_fails_the_control(tmp_path, monkeypatch):
    engine = create_fixture_engine(tmp_path)
    monkeypatch.setattr(
        provenance_controls.ProvenanceAuditor, "verify", lambda *_: {"valid": False}
    )
    with pytest.raises(RuntimeError, match="failed verification"):
        provenance_controls.simulate_case(
            engine, "Disease::D1", "Compound::C1", "source:Hand-counted fixture", draws=1
        )
