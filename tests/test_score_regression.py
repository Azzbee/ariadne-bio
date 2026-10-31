"""The historical-score verifier must detect changes and never preserve a stale pass."""

import json

import pytest

from app.graph_engine import GraphEngine
from scripts import verify_assessments
from tests.test_graph_engine import create_fixture_engine


def test_score_regression_compares_every_pair_in_all_sixteen_scenarios(tmp_path):
    """Include isolated pairs and exact array fingerprints, not just ranking leaders."""
    reference = create_fixture_engine(tmp_path)
    result = verify_assessments.compare_scores(reference, GraphEngine(tmp_path))
    assert result["status"] == "passed"
    assert result["compared_scores"] == 4 * 2 * 16
    assert result["exclusion_configurations"] == 16
    assert result["max_absolute_difference"] == 0
    assert result["unequal_scores"] == 0
    assert all(
        row["baseline_scores_sha256"] == row["current_scores_sha256"] for row in result["scenarios"]
    )


def test_score_regression_detects_one_changed_unsupported_pair(tmp_path, monkeypatch):
    """A change hidden by supported-only rankings must still fail the regression gate."""
    reference = create_fixture_engine(tmp_path)
    current = GraphEngine(tmp_path)
    original_scores = current.score_matrix

    def changed_scores(excluded):
        scores = original_scores(excluded)
        if not excluded:
            scores[0, 0] += 0.125
        return scores

    monkeypatch.setattr(current, "score_matrix", changed_scores)
    result = verify_assessments.compare_scores(reference, current)
    assert result["status"] == "failed"
    assert result["compared_scores"] == 128
    assert result["unequal_scores"] == 1
    assert result["max_absolute_difference"] == 0.125


def test_historical_source_is_not_executed_unless_its_checksum_matches(tmp_path, monkeypatch):
    """The reference import is restricted to the reviewed immutable source bytes."""
    monkeypatch.setattr(
        verify_assessments.subprocess, "check_output", lambda *_args, **_kwargs: b"wrong source"
    )
    with pytest.raises(RuntimeError, match="pinned checksum"):
        verify_assessments.load_baseline(tmp_path)


def test_failed_verification_replaces_old_pass_and_removes_stale_examples(tmp_path, monkeypatch):
    """A missing historical checkout must not leave an earlier successful report behind."""
    (tmp_path / "score-regression.json").write_text('{"status":"passed"}')
    for name in verify_assessments.EXAMPLE_COMPOUNDS:
        (tmp_path / f"assessment-{name}-interacts.json").write_text('{"old":true}')

    def absent_reference(_data_dir):
        raise RuntimeError("Reference commit is absent")

    monkeypatch.setattr(verify_assessments, "load_baseline", absent_reference)
    with pytest.raises(RuntimeError, match="absent"):
        verify_assessments.verify(tmp_path / "data", tmp_path)
    assert json.loads((tmp_path / "score-regression.json").read_text())["status"] == "failed"
    assert not list(tmp_path.glob("assessment-*-interacts.json"))
