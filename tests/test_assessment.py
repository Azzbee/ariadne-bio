"""Independent arithmetic and persistence checks for selected-pair explanations."""

import copy
import itertools
import json
import math

import numpy as np
import pytest

from app.graph_engine import FAMILIES, FEATURE_NAMES, GraphEngine
from tests.test_graph_engine import create_fixture_engine, tiny_graph

EXCLUSIONS = [
    choice for size in range(5) for choice in itertools.combinations(sorted(FAMILIES), size)
]


@pytest.mark.parametrize("excluded", EXCLUSIONS)
def test_every_pair_assessment_reconstructs_fixed_model_in_every_scenario(tmp_path, excluded):
    """Include isolated pairs and all family combinations, not just the visible top-k."""
    engine = create_fixture_engine(tmp_path)
    original_model = copy.deepcopy(engine.model)
    scores = engine.score_matrix(excluded)
    values = engine.feature_matrix(excluded)
    for disease_index, disease in enumerate(engine.entities["Disease"]):
        ranked = {
            item["id"]: item["rank"]
            for item in engine.rankings(disease, exclude=excluded)["candidates"]
        }
        for compound_index, compound in enumerate(engine.entities["Compound"]):
            result = engine.assessment(disease, compound, exclude=excluded)
            assert result["current"]["score"] == scores[compound_index, disease_index]
            assert result["current"]["rank"] == ranked.get(compound)
            assert result["current"]["supported"] == (compound in ranked)
            terms = result["decomposition"]["features"]
            np.testing.assert_array_equal(
                [term["value_after"] for term in terms], values[compound_index, disease_index]
            )
            for state_name, suffix in (("baseline", "before"), ("current", "after")):
                logit = result["decomposition"]["intercept"] + math.fsum(
                    term[f"contribution_{suffix}"] for term in terms
                )
                assert logit == pytest.approx(result[state_name]["logit"], abs=1e-12)
                assert 1 / (1 + math.exp(-logit)) == pytest.approx(
                    result[state_name]["score"], abs=1e-12
                )
            assert math.fsum(term["contribution_delta"] for term in terms) == pytest.approx(
                result["delta"]["logit"], abs=1e-12
            )
            assert result["delta"]["score"] == (
                result["current"]["score"] - result["baseline"]["score"]
            )
    assert engine.model == original_model
    np.testing.assert_array_equal(engine.score_matrix(excluded), scores)


def test_hand_calculated_scaled_contributions_include_centering_and_negative_terms(tmp_path):
    """An explicit asymmetric model catches missing centering, scaling and sign errors."""
    create_fixture_engine(tmp_path)
    model_path = tmp_path / "model.json"
    model = json.loads(model_path.read_text())
    model.update(
        mean=[0.25, -0.5, 0.75, 1.0, 0.5, -0.25, 0.1, 0.2],
        scale=[2.0, 3.0, 4.0, 1.5, 2.5, 0.5, 0.75, 1.25],
        coefficients=[0.8, 2.0, -0.1, 0.3, -0.5, 1.4, -0.7, -1.2],
        intercept=-0.3,
    )
    model_path.write_text(json.dumps(model))
    engine = GraphEngine(tmp_path)
    result = engine.assessment("Disease::D1", "Compound::C2", ["INTERACTS"])
    # Hand-counted C2--D1 has paths (0, 2, 2), binding degree 1 and disease degree 2.
    expected_before = [
        0,
        math.log(3),
        math.log(3),
        0,
        math.log(1 + math.sqrt(2)),
        math.log(1 + math.sqrt(2)),
        math.log(2),
        math.log(3),
    ]
    expected_after = list(expected_before)
    expected_after[1] = expected_after[4] = 0
    assert result["decomposition"]["reference"] == "training_mean"
    assert result["decomposition"]["units"] == "logit"
    terms = result["decomposition"]["features"]
    assert [term["name"] for term in terms] == FEATURE_NAMES
    for index, term in enumerate(terms):
        for suffix, expected in (("before", expected_before), ("after", expected_after)):
            standardized = (expected[index] - model["mean"][index]) / model["scale"][index]
            assert term[f"value_{suffix}"] == pytest.approx(expected[index])
            assert term[f"standardized_{suffix}"] == pytest.approx(standardized)
            assert term[f"contribution_{suffix}"] == pytest.approx(
                model["coefficients"][index] * standardized
            )
    assert terms[0]["value_before"] == 0
    assert terms[0]["contribution_before"] != 0  # Zero input is not the training mean.
    assert terms[1]["contribution_delta"] < 0
    assert terms[4]["contribution_delta"] > 0  # Removing a negative term raises this component.
    assert result["model"]["version"] is None  # No invented fixture model version.
    assert len(result["model"]["model_sha256"]) == 64
    assert result["model"] == engine.assessment("Disease::D1", "Compound::C2")["model"]


def test_unchanged_rank_does_not_hide_score_or_evidence_change(tmp_path):
    """Rank #1 remains #1 even after a positive pathway contribution disappears."""
    result = create_fixture_engine(tmp_path).assessment(
        "Disease::D1", "Compound::C2", ["PARTICIPATES"]
    )
    assert result["baseline"]["rank"] == result["current"]["rank"] == 1
    assert result["delta"]["rank"] == 0
    assert result["delta"]["score"] < 0
    assert result["delta"]["evidence_count"] == -2
    assert result["delta"]["logit"] == pytest.approx(-0.1 * math.log(3))


def test_off_shortlist_and_unsupported_compounds_keep_independent_assessments(tmp_path):
    """An explicit compound never becomes another candidate merely because its rank drops."""
    engine = create_fixture_engine(tmp_path)
    top = engine.rankings("Disease::D1", ["INTERACTS"], limit=1)["candidates"][0]
    off_shortlist = engine.assessment("Disease::D1", "Compound::C2", ["INTERACTS"])
    assert top["id"] == "Compound::C1"
    assert off_shortlist["compound"]["id"] == "Compound::C2"
    assert off_shortlist["baseline"]["rank"] == 1
    assert off_shortlist["current"]["rank"] == 3
    assert off_shortlist["delta"]["rank"] == -2
    removed = engine.assessment("Disease::D1", "Compound::C2", ["BINDS"])
    assert removed["current"]["rank"] is None
    assert removed["delta"]["rank"] is None
    assert removed["current"]["supported"] is False
    assert removed["current"]["evidence_count"] == 0
    assert removed["current"]["score_status"] == "unsupported_diagnostic"
    assert math.isfinite(removed["current"]["score"])
    assert removed["current"]["score"] == engine.score_matrix(["BINDS"])[2, 0]
    isolated = engine.assessment("Disease::D1", "Compound::C0")
    assert isolated["baseline"] == isolated["current"]
    assert isolated["current"]["rank"] is None
    assert isolated["delta"]["logit"] == isolated["delta"]["score"] == 0


@pytest.mark.parametrize(
    "disease,compound,message",
    [
        ("Disease::absent", "Compound::C1", "Unknown disease"),
        ("Compound::C1", "Compound::C1", "Unknown disease"),
        ("Disease::D1", "Gene::G1", "Unknown compound"),
        ("Disease::D1", "Compound::absent", "Unknown compound"),
    ],
)
def test_assessment_rejects_unknown_and_wrong_type_ids(tmp_path, disease, compound, message):
    """No selected-pair lookup can silently substitute a resolvable entity."""
    with pytest.raises(KeyError, match=message):
        create_fixture_engine(tmp_path).assessment(disease, compound)


def test_assessment_rejects_invalid_exclusions_and_missing_model(tmp_path):
    """Untrained data and unsupported family names cannot produce made-up explanations."""
    engine = create_fixture_engine(tmp_path)
    with pytest.raises(ValueError, match="Unknown evidence"):
        engine.assessment("Disease::D1", "Compound::C1", ["TREATS"])
    (tmp_path / "model.json").unlink()
    with pytest.raises(RuntimeError, match="evaluate"):
        GraphEngine(tmp_path).assessment("Disease::D1", "Compound::C1")


def test_pair_assessments_reuse_bulk_scores_without_rebuilding_feature_tensors(
    tmp_path, monkeypatch
):
    """Exporting many compounds must not trigger another large tensor per selected pair."""
    engine = create_fixture_engine(tmp_path)
    for excluded in EXCLUSIONS:
        engine.score_matrix(excluded)

    def forbidden_recomputation(*_args, **_kwargs):
        pytest.fail("A cached scenario was recomputed while explaining a single pair")

    monkeypatch.setattr(engine, "feature_matrix", forbidden_recomputation)
    for excluded in EXCLUSIONS:
        for compound in engine.entities["Compound"]:
            engine.assessment("Disease::D1", compound, excluded)


def test_assessment_response_mutation_and_label_changes_do_not_change_inference(tmp_path):
    """Displayed records and treatment flags cannot corrupt the fixed-model explanation."""
    engine = create_fixture_engine(tmp_path)
    response = engine.assessment("Disease::D1", "Compound::C1")
    original = copy.deepcopy(response)
    response["decomposition"]["features"][0]["contribution_before"] = 1000
    response["current"]["score"] = -1
    assert engine.assessment("Disease::D1", "Compound::C1") == original
    assert engine.assessment("Disease::D1", "Compound::C1", "INTERACTS,INTERACTS") == (
        engine.assessment("Disease::D1", "Compound::C1", ["INTERACTS"])
    )
    graph = tiny_graph()
    graph["treatments"] = []
    without_labels = create_fixture_engine(tmp_path, graph).assessment(
        "Disease::D1", "Compound::C1"
    )
    assert original["known_treatment"] is True
    assert without_labels["known_treatment"] is False
    assert original["decomposition"] == without_labels["decomposition"]
    assert original["current"] == without_labels["current"]
