"""Independent correctness, timing fairness and honest scaling-study publication."""

from copy import deepcopy
import hashlib
import json

import pytest

from app import audit_numerics
from app.binding_audit import certificate_digest
from app.graph_engine import GraphEngine
from app.mixed_audit import MixedAuditor
from scripts import benchmark_mixed_scaling as scaling
from tests.test_binding_audit import _oracle


def fixture_engine(tmp_path):
    """Use a small, retained-byte instance of the same deterministic generator."""
    scaling.write_inputs(tmp_path, 4, 2, 101)
    return GraphEngine(tmp_path)


def test_generator_is_reproducible_and_preserves_predeclared_difficulties(tmp_path):
    first = scaling.write_inputs(tmp_path / "first", 8, 8, 202)
    second = scaling.write_inputs(tmp_path / "second", 8, 8, 202)
    assert first == second
    graph, model, specification = scaling.synthetic_inputs(8, 8, 202)
    assert specification == {"compounds": 8, "source_groups": 8, "seed": 202}
    assert scaling.synthetic_inputs(8, 8, 203) != (graph, model, specification)
    bindings = [edge for edge in graph["edges"] if edge["type"] == "BINDS"]
    assert len(bindings) == 32
    assert all(
        sum(edge["source"] == f"Compound::{index:04d}" for edge in bindings) == 4
        for index in range(8)
    )
    assert any(not edge["sources"] for edge in bindings)
    assert any(len(edge["sources"]) > 1 for edge in bindings)
    assert len({label for edge in bindings for label in edge["sources"]}) == 8
    assert any(value < 0 for value in model["coefficients"])
    assert any(value > 0 for value in model["coefficients"])
    assert all(value > 0 for value in model["scale"])
    assert GraphEngine(tmp_path / "first").model == model


@pytest.mark.parametrize(
    "values", [(True, 4, 101), (2, 4, 101), (8, 0, 101), (8, 17, 101), (8, 4, -1)]
)
def test_generator_rejects_invalid_protocol_values(values):
    with pytest.raises(ValueError, match="Invalid synthetic"):
        scaling.synthetic_inputs(*values)


def test_all_three_arithmetic_caches_are_cleared():
    for name in ("_log1p", "_sqrt", "_sigmoid"):
        function = getattr(audit_numerics, name)
        function(2.0)
        assert function.cache_info().currsize > 0
    scaling._clear_arithmetic_caches()
    assert all(
        getattr(audit_numerics, name).cache_info().currsize == 0
        for name in ("_log1p", "_sqrt", "_sigmoid")
    )


def test_sparse_reference_matches_independent_literal_paths_and_scalar_scores(tmp_path):
    engine = fixture_engine(tmp_path)
    graph = json.loads((tmp_path / "graph.json").read_text())
    reference = scaling.NaiveReference(engine)
    actions = list(reference.actions())
    assert len(actions) == 1 + len(reference.coordinates) + sum(
        1 + len(reference.coordinates) - len(members) for members in reference.groups.values()
    )
    selected_actions = [
        actions[0],
        actions[1],
        next(row for row in actions if row[0] and not row[1]),
        next(row for row in actions if row[0] and row[1]),
    ]
    for selected, residual, removed in selected_actions:
        assert not residual or not selected or residual[0] not in reference.groups[selected[0]]
        literal = _oracle(graph, engine.model, scaling.DISEASE, removed)
        assert reference.state(removed) == literal
        focus = engine.entities["Compound"][0]
        assert reference.state(removed, [focus]) == {focus: literal[focus]}


def test_two_trials_compare_every_cell_and_alternate_methods(tmp_path, monkeypatch):
    calls = []
    original = scaling._timed_method

    def observe(engine, foci, method):
        calls.append(method)
        return original(engine, foci, method)

    monkeypatch.setattr(scaling, "_timed_method", observe)
    result = scaling.run_study(tmp_path, sizes=(4,), group_counts=(2,), seeds=(101,), trials=2)
    assert result["status"] == "passed"
    assert not result["protocol"]["is_full_predeclared_grid"]
    assert result["coverage"]["datasets"] == 1
    assert result["coverage"]["trials"] == 2
    assert result["coverage"]["certificates_verified"] == 6
    assert result["coverage"]["frontier_cells_compared"] == 24
    assert result["coverage"]["failed_checks"] == 0
    assert calls == ["envelope", "naive", "naive", "envelope"]
    row = result["datasets"][0]
    assert row["trials"][0]["certificate_sha256"] == row["trials"][1]["certificate_sha256"]
    assert (
        row["trials"][0]["full_world_recomputations"]
        == row["certificates"][0]["results"][-1]["covered_action_representations"]
    )
    for name, value in row["input_file_sha256"].items():
        assert (
            hashlib.sha256(
                (tmp_path / "inputs" / row["dataset_id"] / name).read_bytes()
            ).hexdigest()
            == value
        )
    assert all(trial["verification_seconds"] > 0 for trial in row["trials"])


def test_rehashed_false_frontier_is_rejected_before_verifier(tmp_path):
    engine = fixture_engine(tmp_path)
    foci = engine.entities["Compound"][:3]
    auditor = MixedAuditor(engine)
    certificates = [auditor.audit(scaling.DISEASE, compound, top_k=3) for compound in foci]
    reference, _ = scaling.NaiveReference(engine).solve(foci)
    certificates[0]["results"][-1]["worst_supported_rank"] += 1
    certificates[0]["certificate_sha256"] = certificate_digest(certificates[0])
    with pytest.raises(RuntimeError, match="Exhaustive frontier mismatch"):
        scaling.compare_and_verify(engine, foci, certificates, reference)


def test_corrupted_witness_is_caught_by_literal_matrix_replay(tmp_path):
    engine = fixture_engine(tmp_path)
    foci = engine.entities["Compound"][:3]
    auditor = MixedAuditor(engine)
    certificates = [auditor.audit(scaling.DISEASE, compound, top_k=3) for compound in foci]
    reference, _ = scaling.NaiveReference(engine).solve(foci)
    certificates[0]["results"][-1]["rank_witness"]["focus"]["after"]["score"] = 0.0
    certificates[0]["certificate_sha256"] = certificate_digest(certificates[0])
    with pytest.raises(RuntimeError, match="Independent witness replay mismatch"):
        scaling.compare_and_verify(engine, foci, certificates, reference)


def test_ratios_are_paired_measurements_and_keep_setup_separate():
    data = [
        {
            "configuration": {"compounds": 8, "source_groups": 4},
            "trials": [
                {
                    "timing": {
                        "naive": {"setup_seconds": 1.0, "solve_seconds": 8.0},
                        "envelope": {"setup_seconds": 2.0, "solve_seconds": 2.0},
                    }
                },
                {
                    "timing": {
                        "naive": {"setup_seconds": 1.0, "solve_seconds": 2.0},
                        "envelope": {"setup_seconds": 2.0, "solve_seconds": 1.0},
                    }
                },
            ],
        }
    ]
    result = scaling.aggregate(data)[0]
    assert result["paired_naive_over_envelope_solve_ratio"] == {
        "minimum": 2.0,
        "median": 3.0,
        "maximum": 4.0,
    }
    assert result["paired_naive_over_envelope_setup_and_solve_ratio"] == {
        "minimum": 1.0,
        "median": 1.625,
        "maximum": 2.25,
    }


def test_source_changes_and_unclean_checkpoint_fail_closed(tmp_path, monkeypatch):
    original = scaling._source_identity
    identity = original()
    identity["working_tree_dirty"] = True
    monkeypatch.setattr(scaling, "_source_identity", lambda: identity)
    with pytest.raises(RuntimeError, match="clean source checkpoint"):
        scaling.run_study(tmp_path, require_clean=True)
    calls = []

    def changed():
        value = deepcopy(identity)
        if calls:
            value["file_sha256"]["app/mixed_audit.py"] = "changed"
        calls.append(True)
        return value

    monkeypatch.setattr(scaling, "_source_identity", changed)
    with pytest.raises(RuntimeError, match="Scaling scientific source changed"):
        scaling.run_study(tmp_path, sizes=(4,), group_counts=(2,), seeds=(101,), trials=1)


def test_failed_cli_invalidates_both_prior_success_reports(tmp_path, monkeypatch):
    for filename in (scaling.REPORT_NAME, scaling.SUMMARY_NAME):
        (tmp_path / filename).write_text('{"status":"passed"}')

    def fail(*_args, **_kwargs):
        raise RuntimeError("Controlled study failure")

    monkeypatch.setattr(scaling, "run_study", fail)
    with pytest.raises(RuntimeError, match="Controlled study failure"):
        scaling.main(["--output-dir", str(tmp_path)])
    assert all(
        json.loads((tmp_path / name).read_text())["status"] == "failed"
        for name in (scaling.REPORT_NAME, scaling.SUMMARY_NAME)
    )


def test_cli_publishes_hashed_report_and_cannot_claim_partial_grid_is_full(tmp_path, monkeypatch):
    original = scaling.run_study

    def quick(directory, **_kwargs):
        return original(directory, sizes=(4,), group_counts=(2,), seeds=(101,), trials=1)

    monkeypatch.setattr(scaling, "run_study", quick)
    scaling.main(["--output-dir", str(tmp_path)])
    report = json.loads((tmp_path / scaling.REPORT_NAME).read_text())
    summary = json.loads((tmp_path / scaling.SUMMARY_NAME).read_text())
    assert summary["status"] == report["status"] == "passed"
    assert "datasets" not in summary
    assert not report["protocol"]["is_full_predeclared_grid"]
    assert summary["full_report"] == {
        "file": scaling.REPORT_NAME,
        "sha256": hashlib.sha256((tmp_path / scaling.REPORT_NAME).read_bytes()).hexdigest(),
    }


def test_cli_creates_a_new_nested_output_directory(tmp_path, monkeypatch):
    original = scaling.run_study
    output = tmp_path / "brand-new" / "nested-scaling-output"
    assert not output.exists()

    def quick(directory, **_kwargs):
        assert directory == output and directory.is_dir()
        return original(directory, sizes=(4,), group_counts=(2,), seeds=(101,), trials=1)

    monkeypatch.setattr(scaling, "run_study", quick)
    scaling.main(["--output-dir", str(output)])
    assert json.loads((output / scaling.REPORT_NAME).read_text())["status"] == "passed"
    assert json.loads((output / scaling.SUMMARY_NAME).read_text())["status"] == "passed"


@pytest.mark.parametrize(
    "kwargs", [{"trials": True}, {"trials": 0}, {"sizes": ()}, {"seeds": (101, 101)}]
)
def test_empty_duplicate_or_invalid_study_is_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        scaling.run_study(tmp_path, **kwargs)
