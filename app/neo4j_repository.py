"""Bounded Neo4j queries and genuine GDS execution on an evidence-only graph."""

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any

from neo4j import GraphDatabase, Query

from app.config import Settings

RELATIONS = {"BINDS", "ASSOCIATES", "INTERACTS", "PARTICIPATES"}
LABELS = {"Compound", "Gene", "Disease", "Pathway"}

PATH_QUERIES = {
    "direct": (
        "MATCH p=(c:Compound {id:$compound})-[:BINDS]->(g:Gene)"
        "<-[:ASSOCIATES]-(d:Disease {id:$disease}) "
        "RETURN p LIMIT $limit"
    ),
    "interaction": (
        "MATCH p=(c:Compound {id:$compound})-[:BINDS]->(g:Gene)"
        "-[:INTERACTS]-(h:Gene)<-[:ASSOCIATES]-(d:Disease {id:$disease}) "
        "WHERE g <> h RETURN p LIMIT $limit"
    ),
    "pathway": (
        "MATCH p=(c:Compound {id:$compound})-[:BINDS]->(g:Gene)"
        "-[:PARTICIPATES]->(pw:Pathway)<-[:PARTICIPATES]-(h:Gene)"
        "<-[:ASSOCIATES]-(d:Disease {id:$disease}) "
        "WHERE g <> h RETURN p LIMIT $limit"
    ),
}
PATH_RELATIONS = {
    "direct": {"BINDS", "ASSOCIATES"},
    "interaction": {"BINDS", "ASSOCIATES", "INTERACTS"},
    "pathway": {"BINDS", "ASSOCIATES", "PARTICIPATES"},
}
METAPATHS = {
    "direct": "Compound–Gene–Disease",
    "interaction": "Compound–Gene–Gene–Disease",
    "pathway": "Compound–Gene–Pathway–Gene–Disease",
}


def _properties(item: dict[str, Any]) -> dict[str, Any]:
    """Serialize nested upstream metadata without discarding it."""
    values = {k: v for k, v in item.items() if k not in {"source", "target", "label"}}
    for key, value in list(values.items()):
        if isinstance(value, dict) or (
            isinstance(value, list) and any(isinstance(x, (dict, list)) for x in value)
        ):
            values[key] = json.dumps(value, sort_keys=True)
    return values


def _load_verified_graph(data_dir: Path) -> tuple[dict, dict]:
    """Validate source identity and the full schema before the first database write."""
    manifest = json.loads((data_dir / "manifest.json").read_text())
    graph_path = data_dir / "graph.json"
    digest = sha256()
    with graph_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if manifest.get("graph_sha256") and digest.hexdigest() != manifest["graph_sha256"]:
        raise ValueError("Processed graph checksum mismatch; import refused")
    graph = json.loads(graph_path.read_text())
    if any(node["label"] not in LABELS for node in graph["nodes"]):
        raise ValueError("Unsupported node label; import refused before database writes")
    if any(edge["type"] not in RELATIONS for edge in graph["edges"]):
        raise ValueError("Forbidden evidence relationship; import refused before database writes")
    if not manifest.get("dataset_sha256"):
        raise ValueError("Dataset manifest must contain the source SHA256")
    return graph, manifest


class Neo4jRepository:
    """Fixed query library: users and language models never provide Cypher."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            connection_timeout=10,
            max_connection_pool_size=10,
        )
        self._projection_lock = Lock()
        self._projections: set[str] = set()

    def close(self) -> None:
        """Close pooled connections on application shutdown."""
        self.driver.close()

    def run(self, cypher: str, params: dict | None = None, *, write=False) -> list[dict]:
        """Run one internal parameterized statement with a transaction timeout."""
        query = Query(cypher, timeout=self.settings.query_timeout)
        with self.driver.session(
            database=self.settings.neo4j_database,
            default_access_mode="WRITE" if write else "READ",
        ) as session:
            return session.run(query, params or {}).data()

    def verify(self, expected_sha256: str | None = None) -> dict:
        """Verify connectivity and optionally bind cached features to this dataset."""
        self.driver.verify_connectivity()
        rows = self.run(
            "MATCH (d:Dataset {id:'hetionet-v1.0'}) "
            "RETURN d.sha256 AS sha256, d.nodes AS nodes, d.edges AS edges"
        )
        if not rows:
            raise ValueError("Neo4j is empty. Run make ingest to load the evidence graph.")
        if expected_sha256 and rows[0]["sha256"] != expected_sha256:
            raise ValueError("Neo4j dataset checksum does not match the feature artifacts")
        return rows[0]

    def ingest(self, data_dir: Path, batch_size: int = 1000) -> dict:
        """Idempotently ingest typed evidence; treatment labels stay outside Neo4j."""
        graph, manifest = _load_verified_graph(data_dir)
        for label in ["Entity", "Compound", "Gene", "Disease", "Pathway", "Dataset"]:
            self.run(
                f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.id IS UNIQUE",
                write=True,
            )
        for label in ["Disease", "Compound"]:
            self.run(
                f"CREATE INDEX {label.lower()}_name IF NOT EXISTS " f"FOR (n:{label}) ON (n.name)",
                write=True,
            )
        groups: dict[str, list] = defaultdict(list)
        for node in graph["nodes"]:
            groups[node["label"]].append(_properties(node))
        for label, nodes in groups.items():
            for start in range(0, len(nodes), batch_size):
                self.run(
                    f"UNWIND $rows AS row MERGE (n:Entity:{label} {{id:row.id}}) " "SET n += row",
                    {"rows": nodes[start : start + batch_size]},
                    write=True,
                )
        edges: dict[str, list] = defaultdict(list)
        for edge in graph["edges"]:
            edges[edge["type"]].append(
                {
                    "source": edge["source"],
                    "target": edge["target"],
                    "props": _properties(edge),
                }
            )
        for relation, records in edges.items():
            for start in range(0, len(records), batch_size):
                self.run(
                    "UNWIND $rows AS row MATCH (a:Entity {id:row.source}) "
                    "MATCH (b:Entity {id:row.target}) "
                    f"MERGE (a)-[r:{relation} {{id:row.props.id}}]->(b) SET r += row.props",
                    {"rows": records[start : start + batch_size]},
                    write=True,
                )
        checksum = manifest["dataset_sha256"]
        self.run(
            "MERGE (d:Dataset {id:'hetionet-v1.0'}) "
            "SET d.sha256=$checksum,d.nodes=$nodes,d.edges=$edges",
            {"checksum": checksum, "nodes": len(graph["nodes"]), "edges": len(graph["edges"])},
            write=True,
        )
        self.run("CALL db.awaitIndexes(120)", write=True)
        return self.verify(checksum)

    def evidence(self, disease_id: str, compound_id: str, exclude=(), limit=12) -> dict:
        """Return representative actual Neo4j paths, sharing the display budget fairly."""
        excluded = set(exclude)
        nodes, edges, paths = {}, {}, []
        families = [k for k, rels in PATH_RELATIONS.items() if not rels & excluded]
        family_limit = max(1, (limit + max(len(families), 1) - 1) // max(len(families), 1))
        for family in families:
            with self.driver.session(
                database=self.settings.neo4j_database, default_access_mode="READ"
            ) as session:
                results = session.run(
                    Query(PATH_QUERIES[family], timeout=self.settings.query_timeout),
                    disease=disease_id,
                    compound=compound_id,
                    limit=family_limit,
                )
                for record in results:
                    if len(paths) >= limit:
                        break
                    path = record["p"]
                    node_ids, edge_ids = [], []
                    for node in path.nodes:
                        obj = dict(node)
                        obj["label"] = next(label for label in node.labels if label in LABELS)
                        nodes[obj["id"]] = obj
                        node_ids.append(obj["id"])
                    for relation in path.relationships:
                        obj = dict(relation)
                        obj.update(
                            source=relation.start_node["id"],
                            target=relation.end_node["id"],
                            type=relation.type,
                        )
                        edges[obj["id"]] = obj
                        edge_ids.append(obj["id"])
                    path_id = "p_" + sha256("|".join(edge_ids).encode()).hexdigest()[:16]
                    paths.append(
                        {
                            "id": path_id,
                            "node_ids": node_ids,
                            "edge_ids": edge_ids,
                            "metapath": METAPATHS[family],
                            "family": family,
                            "weight": 1.0,
                        }
                    )
        return {
            "nodes": list(nodes.values()),
            "edges": list(edges.values()),
            "paths": paths,
            "execution_backend": "neo4j",
            "selection": (
                "Bounded Neo4j samples divided by metapath family; database traversal order"
            ),
        }

    def similar(self, compound_id: str, limit=10) -> dict:
        """Compute exact target-neighborhood Jaccard using aggregate Cypher."""
        rows = self.run(
            "MATCH (c:Compound {id:$id})-[:BINDS]->(g:Gene) "
            "WITH c,collect(DISTINCT g) AS targets "
            "UNWIND targets AS g MATCH (other:Compound)-[:BINDS]->(g) "
            "WHERE other <> c WITH targets,other,count(DISTINCT g) AS overlap "
            "MATCH (other)-[:BINDS]->(h:Gene) "
            "WITH other,overlap,size(targets) AS leftSize,count(DISTINCT h) AS rightSize "
            "WITH other,overlap,leftSize+rightSize-overlap AS unionSize "
            "RETURN other.id AS id,other.name AS name,overlap AS shared_targets,"
            "toFloat(overlap)/unionSize AS similarity "
            "ORDER BY similarity DESC,id LIMIT $limit",
            {"id": compound_id, "limit": limit},
        )
        return {
            "items": rows,
            "algorithm": "target-neighborhood Jaccard",
            "execution_backend": "neo4j",
        }

    def _project(self, name: str, targets_only=False) -> None:
        """Create a namespaced evidence-only GDS projection once, safely across threads."""
        with self._projection_lock:
            if name in self._projections:
                return
            exists = self.run("RETURN gds.graph.exists($name) AS present", {"name": name})
            if not exists[0]["present"]:
                labels = ["Compound", "Gene"] if targets_only else sorted(LABELS)
                relations = (
                    {"BINDS": {"orientation": "NATURAL"}}
                    if targets_only
                    else {relation: {"orientation": "UNDIRECTED"} for relation in sorted(RELATIONS)}
                )
                self.run(
                    "CALL gds.graph.project($name,$labels,$relations) "
                    "YIELD graphName RETURN graphName",
                    {"name": name, "labels": labels, "relations": relations},
                    write=True,
                )
            self._projections.add(name)

    def algorithms(self, disease_id: str, limit=10) -> dict:
        """GDS personalized PageRank over the label-free evidence graph."""
        self._project("ariadne-evidence-v1")
        started = perf_counter()
        rows = self.run(
            "MATCH (d:Disease {id:$id}) WITH d "
            "CALL gds.pageRank.stream('ariadne-evidence-v1',"
            "{sourceNodes:[d],dampingFactor:0.85,maxIterations:100,tolerance:0.0000001,"
            "concurrency:2}) YIELD nodeId,score "
            "WITH gds.util.asNode(nodeId) AS n,score WHERE n:Compound "
            "RETURN n.id AS id,n.name AS name,score ORDER BY score DESC,id LIMIT $limit",
            {"id": disease_id, "limit": limit},
        )
        return {
            "algorithm": "personalized PageRank",
            "execution_backend": "neo4j-gds",
            "version": self.run("RETURN gds.version() AS version")[0]["version"],
            "projection": "ariadne-evidence-v1",
            "items": rows,
            "elapsed_ms": round((perf_counter() - started) * 1000, 2),
            "interpretation": "Graph proximity, not a treatment efficacy probability.",
        }

    def gds_similarity(self, compound_id: str, limit=10) -> dict:
        """Second genuine GDS algorithm on the bipartite target projection."""
        self._project("ariadne-targets-v1", targets_only=True)
        rows = self.run(
            "MATCH (c:Compound {id:$id}) WITH c "
            "CALL gds.nodeSimilarity.filtered.stream('ariadne-targets-v1',"
            "{sourceNodeFilter:[c],targetNodeFilter:'Compound',topK:$limit,"
            "similarityCutoff:0.000001,concurrency:2}) "
            "YIELD node1,node2,similarity "
            "WITH gds.util.asNode(node2) AS n,similarity "
            "RETURN n.id AS id,n.name AS name,similarity "
            "ORDER BY similarity DESC,id LIMIT $limit",
            {"id": compound_id, "limit": limit},
        )
        return {
            "algorithm": "GDS filtered node similarity (Jaccard)",
            "execution_backend": "neo4j-gds",
            "items": rows,
            "projection": "ariadne-targets-v1",
        }

    def profile_lookup(self, entity_id: str, repeats=7) -> dict:
        """Measure equivalent scan and indexed lookup without dropping production indexes."""
        variants = {
            "scan": "MATCH (n:Entity) WHERE toString(n.id) = $id RETURN n.id",
            "indexed": "MATCH (n:Entity {id:$id}) RETURN n.id",
        }
        report = {}
        for name, cypher in variants.items():
            times = []
            self.run(cypher, {"id": entity_id})  # Warm each plan before measurement.
            for _ in range(repeats):
                start = perf_counter()
                self.run(cypher, {"id": entity_id})
                times.append(round((perf_counter() - start) * 1000, 3))
            with self.driver.session(database=self.settings.neo4j_database) as session:
                summary = session.run("PROFILE " + cypher, id=entity_id).consume()
                profile = summary.profile
            report[name] = {
                "latency_ms": times,
                "median_ms": sorted(times)[repeats // 2],
                "profile": profile,
            }
        return report
