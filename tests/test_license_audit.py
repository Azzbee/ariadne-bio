"""License inventory must preserve ambiguity instead of fabricating permission."""

import hashlib
import json

import pytest

from scripts.audit_licenses import audit_file, inventory


def graph_with(records=(), edges=(), treatments=()):
    """Minimal prepared-data contract with an explicit frozen input identity."""
    return {
        "nodes": list(records),
        "edges": list(edges),
        "treatments": list(treatments),
        "metadata": {"dataset": "fixture", "dataset_sha256": "source-checksum"},
    }


def test_noncommercial_metadata_never_becomes_mit_or_commercial_clearance():
    graph = graph_with(
        [
            {
                "id": "Compound::1",
                "label": "Compound",
                "data": {"source": "DrugBank", "license": "CC BY-NC 4.0"},
            }
        ]
    )
    report = inventory(graph, "graph-checksum")
    assert report["collections"]["nodes"]["licenses"] == {"CC BY-NC 4.0": 1}
    assert report["summary"]["review_flags"]["noncommercial_text"] == 1
    assert report["legal_clearance"]["commercial_permission"] is None
    assert report["legal_clearance"]["status"] == "not_assessed"


def test_missing_edge_license_and_missing_source_remain_explicit():
    graph = graph_with(edges=[{"id": "e1", "type": "BINDS", "source": "Compound::1"}])
    report = inventory(graph, "hash")
    assert report["summary"]["missing_license_records"] == 1
    assert report["summary"]["missing_source_records"] == 1
    assert report["sources"] == []  # The graph endpoint is not a publisher.


def test_shared_sources_count_one_edge_but_retain_each_cooccurrence():
    edge = {
        "id": "e1",
        "type": "INTERACTS",
        "sources": ["first", "second", "first"],
        "license": "CC BY 4.0",
        "data": {"sources": ["second"], "license": "CC BY 4.0"},
    }
    report = inventory(graph_with(edges=[edge]), "hash")
    assert report["summary"]["records"] == 1
    assert report["summary"]["licenses"] == {"CC BY 4.0": 1}
    assert [source["records"] for source in report["sources"]] == [1, 1]
    assert "not assigned" in report["scope"]["source_license_caveat"]


def test_conflicting_and_unrecognized_declarations_are_preserved():
    edge = {
        "id": "e1",
        "type": "BINDS",
        "license": "CC0 1.0",
        "data": {"license": "Permission needed for product X", "source": "Publisher"},
    }
    report = inventory(graph_with(edges=[edge]), "hash")
    assert report["summary"]["licenses"] == {"CC0 1.0": 1, "Permission needed for product X": 1}
    assert report["summary"]["review_flags"]["multiple_license_declarations"] == 1
    assert report["summary"]["review_flags"]["unrecognized_license_text"] == 1
    assert report["legal_clearance"]["commercial_permission"] is None


def test_separate_treatment_labels_are_audited_without_becoming_evidence():
    report = inventory(
        graph_with(
            treatments=[{"id": "t1", "type": "TREATS", "sources": ["labels"], "license": "CC0 1.0"}]
        ),
        "hash",
    )
    assert report["collections"]["treatments"]["records"] == 1
    assert report["collections"]["edges"]["records"] == 0
    assert report["sources"][0]["collections"] == {"treatments": 1}


def test_share_alike_marker_is_not_treated_as_noncommercial():
    report = inventory(
        graph_with(
            edges=[{"id": "e1", "type": "BINDS", "license": "ODbL 1.0", "sources": ["database"]}]
        ),
        "hash",
    )
    flags = report["summary"]["review_flags"]
    assert flags["share_alike_text"] == 1
    assert "noncommercial_text" not in flags


def test_inventory_is_deterministic_bound_to_actual_bytes_and_read_only(tmp_path):
    source = tmp_path / "graph.json"
    source.write_text(json.dumps(graph_with()), encoding="utf-8")
    original = source.read_bytes()
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    report = audit_file(source, first)
    audit_file(source, second)
    assert source.read_bytes() == original
    assert first.read_bytes() == second.read_bytes()
    assert report["input"]["graph_sha256"] == hashlib.sha256(original).hexdigest()


@pytest.mark.parametrize("alias", ["same_path", "symlink", "hardlink"])
def test_output_cannot_overwrite_the_source_even_through_an_alias(tmp_path, alias):
    source = tmp_path / "graph.json"
    source.write_text(json.dumps(graph_with()), encoding="utf-8")
    original = source.read_bytes()
    target = source if alias == "same_path" else tmp_path / "alias.json"
    if alias == "symlink":
        target.symlink_to(source)
    elif alias == "hardlink":
        target.hardlink_to(source)
    with pytest.raises(ValueError, match="must not overwrite"):
        audit_file(source, target)
    assert source.read_bytes() == original


@pytest.mark.parametrize("bad_value", [42, {}, ["valid", None]])
def test_malformed_license_metadata_fails_instead_of_disappearing(bad_value):
    with pytest.raises(ValueError, match="Expected text"):
        inventory(graph_with(edges=[{"id": "e1", "license": bad_value}]), "hash")


def test_incomplete_graph_cannot_produce_a_successful_empty_inventory():
    with pytest.raises(ValueError, match="nodes list"):
        inventory({}, "hash")
