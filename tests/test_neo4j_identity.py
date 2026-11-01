"""Import-identity state-machine tests; genuine database tests remain separate."""

from copy import deepcopy
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from app.neo4j_repository import DATASET_ID, Neo4jRepository
from tests.test_graph_engine import tiny_graph


class ImportState(Neo4jRepository):
    """Record mutations and simulate only the import inventory protocol."""

    def __init__(self, *, marker=None, nodes=(), edges=None, drop_edge=False):
        self.markers = [] if marker is None else [deepcopy(marker)]
        self.nodes = set(nodes)
        self.edges = {} if edges is None else dict(edges)
        self.mutations = []
        self.drop_edge = drop_edge
        self.driver = SimpleNamespace(verify_connectivity=lambda: None)

    def run(self, cypher, params=None, *, write=False):
        params = params or {}
        if write:
            self.mutations.append((cypher, deepcopy(params)))
        if cypher.startswith("MATCH (d:Dataset)"):
            return deepcopy(self.markers)
        if cypher.startswith("MATCH (n) WHERE NOT n:Dataset"):
            return [{"nodes": len(self.nodes)}]
        if cypher.startswith("MATCH ()-[r]->()"):
            types = sorted(set(self.edges.values()))
            return [
                {"type": kind, "count": list(self.edges.values()).count(kind)} for kind in types
            ]
        if cypher.startswith("UNWIND") and "MERGE (n:Entity:" in cypher:
            self.nodes.update(row["id"] for row in params["rows"])
        elif cypher.startswith("UNWIND") and "MERGE (a)-[r:" in cypher:
            for row in params["rows"]:
                if not self.drop_edge:
                    self.edges[row["props"]["id"]] = row["props"]["type"]
        elif cypher.startswith("MERGE (d:Dataset"):
            self.markers = [
                {
                    "id": params["dataset_id"],
                    "sha256": params["checksum"],
                    "graph_sha256": params["graph_sha256"],
                    "import_status": "complete",
                    "nodes": params["nodes"],
                    "edges": params["edges"],
                }
            ]
        return []


@pytest.fixture
def prepared(tmp_path):
    """A checksummed input with a stable archive ID and changeable graph bytes."""
    graph = tiny_graph()
    raw = json.dumps(graph).encode()
    (tmp_path / "graph.json").write_bytes(raw)
    manifest = {
        "dataset_sha256": "a" * 64,
        "graph_sha256": sha256(raw).hexdigest(),
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    marker = {
        "id": DATASET_ID,
        "sha256": manifest["dataset_sha256"],
        "graph_sha256": manifest["graph_sha256"],
        "import_status": "complete",
        "nodes": len(graph["nodes"]),
        "edges": len(graph["edges"]),
    }
    return tmp_path, graph, marker


def loaded_state(graph, marker):
    """Construct a previously imported inventory independent of input-file parsing."""
    return ImportState(
        marker=marker,
        nodes=(node["id"] for node in graph["nodes"]),
        edges={edge["id"]: edge["type"] for edge in graph["edges"]},
    )


def test_empty_import_completes_only_after_counted_records_and_is_idempotent(prepared):
    """A complete marker is the last mutation and second import changes no inventory."""
    directory, graph, expected = prepared
    repository = ImportState()
    first = repository.ingest(directory, batch_size=2)
    assert first == expected
    assert repository.mutations[-1][0].startswith("MERGE (d:Dataset")
    nodes, edges = set(repository.nodes), dict(repository.edges)
    second = repository.ingest(directory, batch_size=3)
    assert second == first
    assert repository.nodes == nodes
    assert repository.edges == edges
    assert len(nodes) == len(graph["nodes"])


@pytest.mark.parametrize(
    "change, message",
    [
        ({"graph_sha256": "b" * 64}, "identity mismatch"),
        ({"sha256": "b" * 64}, "identity mismatch"),
        ({"graph_sha256": None}, "legacy imports"),
        ({"import_status": None}, "legacy imports"),
        ({"import_status": "started"}, "legacy imports"),
        ({"id": "another-dataset"}, "unique compatible"),
        ({"edges": 100}, "inventory differs"),
    ],
)
def test_incompatible_existing_import_is_rejected_before_any_mutation(prepared, change, message):
    """Even equal archive IDs cannot authorize a changed prepared-graph import."""
    directory, graph, marker = prepared
    marker.update(change)
    repository = loaded_state(graph, marker)
    before = deepcopy((repository.nodes, repository.edges, repository.markers))
    with pytest.raises(ValueError, match=message):
        repository.ingest(directory)
    assert repository.mutations == []
    assert (repository.nodes, repository.edges, repository.markers) == before


def test_nonempty_unmarked_database_is_preserved(prepared):
    """A failed historical import or unrelated data is never adopted or auto-cleared."""
    directory, _, _ = prepared
    repository = ImportState(nodes=["unrelated-record"])
    with pytest.raises(ValueError, match="isolated empty"):
        repository.ingest(directory)
    assert repository.nodes == {"unrelated-record"}
    assert repository.mutations == []


def test_multiple_dataset_markers_are_rejected_before_writes(prepared):
    """More than one identity cannot be silently collapsed to the first result."""
    directory, graph, marker = prepared
    repository = loaded_state(graph, marker)
    repository.markers.append({**marker, "id": "another-dataset"})
    with pytest.raises(ValueError, match="unique compatible"):
        repository.ingest(directory)
    assert repository.mutations == []


def test_partial_import_never_publishes_complete_identity(prepared):
    """An omitted relationship batch fails inventory verification before certification."""
    directory, _, _ = prepared
    repository = ImportState(drop_edge=True)
    with pytest.raises(ValueError, match="no completed graph identity"):
        repository.ingest(directory)
    assert not repository.markers
    assert not any(query.startswith("MERGE (d:Dataset") for query, _ in repository.mutations)


def test_bad_local_checksum_fails_before_database_queries(prepared):
    """Local artifact validation precedes the first database write or state inspection."""
    directory, _, _ = prepared
    (directory / "graph.json").write_text("{}")
    repository = ImportState()
    with pytest.raises(ValueError, match="checksum mismatch"):
        repository.ingest(directory)
    assert repository.mutations == []


def test_startup_verification_checks_both_identities_and_actual_counts(prepared):
    """Direct startup cannot accept matching archives with different prepared bytes."""
    _, graph, marker = prepared
    repository = loaded_state(graph, marker)
    assert repository.verify(marker["sha256"], marker["graph_sha256"]) == marker
    with pytest.raises(ValueError, match="prepared graph checksum"):
        repository.verify(marker["sha256"], "b" * 64)
    repository.nodes.add("unexpected-record")
    with pytest.raises(ValueError, match="inventory differs"):
        repository.verify(marker["sha256"], marker["graph_sha256"])
    assert repository.mutations == []
