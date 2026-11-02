"""Recorded mixed frontiers must retain their declared source scope and all cells."""

from copy import deepcopy

import pytest

from app.binding_audit import certificate_digest
from scripts.export_snapshot import build_case, validate_case
from tests.test_provenance_api import provenance_fixture


@pytest.fixture(name="recorded_case")
def _recorded_case(tmp_path):
    return build_case(provenance_fixture(tmp_path), "Disease::D1", top_k=2)


def _change_certificate(case, mutation):
    compound = next(iter(case["mixed_audits"]))
    certificate = case["mixed_audits"][compound]["10:1:1"]
    mutation(certificate)
    certificate["certificate_sha256"] = certificate_digest(certificate)
    case["mixed_verifications"][compound]["10:1:1"]["certificate_sha256"] = certificate[
        "certificate_sha256"
    ]


def test_recorded_mixed_frontier_passes_the_complete_export_contract(recorded_case):
    validate_case(recorded_case)


@pytest.mark.parametrize("change", ["missing", "duplicate", "reversed"])
def test_recorded_mixed_frontier_rejects_missing_duplicate_or_reordered_cells(
    recorded_case, change
):
    case = deepcopy(recorded_case)

    def mutate(certificate):
        if change == "missing":
            certificate["results"].pop()
        elif change == "duplicate":
            certificate["results"][-1] = deepcopy(certificate["results"][0])
        else:
            certificate["results"].reverse()

    _change_certificate(case, mutate)
    with pytest.raises(ValueError):
        validate_case(case)


@pytest.mark.parametrize(
    "field,value",
    [
        ("group_kind", "pubmed"),
        ("group_ids", []),
        ("operation", "delete_any_record"),
        ("includes_competitor_changes", False),
    ],
)
def test_recorded_mixed_frontier_rejects_rehashed_scope_drift(recorded_case, field, value):
    case = deepcopy(recorded_case)
    _change_certificate(case, lambda certificate: certificate["scope"].update({field: value}))
    with pytest.raises(ValueError):
        validate_case(case)


@pytest.mark.parametrize("field", ["model_sha256", "graph_sha256", "group_map_sha256", "scorer"])
def test_recorded_mixed_frontier_cannot_silently_use_other_inputs(recorded_case, field):
    case = deepcopy(recorded_case)
    _change_certificate(
        case, lambda certificate: certificate["identity"].update({field: "different"})
    )
    with pytest.raises(ValueError):
        validate_case(case)
