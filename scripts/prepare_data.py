"""Download, verify and stream a provenance-preserving Hetionet evidence graph."""

from __future__ import annotations

import argparse
import bz2
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import urllib.request

import ijson

UPSTREAM_COMMIT = "8a6cc0c5604d0e2908786e4de38af67b8e46ee4a"
DATASET_URL = (
    "https://media.githubusercontent.com/media/hetio/hetionet/"
    f"{UPSTREAM_COMMIT}/hetnet/json/hetionet-v1.0.json.bz2"
)
EXPECTED_SHA256 = "a342ab57e9073e6c02bb5e109d1f16917e6f933be4e5c77ebbaebfa26b984c19"
EXPECTED_NODE_COUNT = 24456
EXPECTED_TREATMENT_COUNT = 755
LABELS = frozenset({"Compound", "Gene", "Disease", "Pathway"})
RELATIONSHIPS = {
    ("Compound", "binds", "Gene"): "BINDS",
    ("Disease", "associates", "Gene"): "ASSOCIATES",
    ("Gene", "interacts", "Gene"): "INTERACTS",
    ("Gene", "participates", "Pathway"): "PARTICIPATES",
}


def file_sha256(path: Path) -> str:
    """Hash a file incrementally, including the compressed dataset bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_dataset(path: Path) -> None:
    """Download atomically; refuse an unexpected upstream payload."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    try:
        with urllib.request.urlopen(DATASET_URL, timeout=120) as response:
            with temporary.open("wb") as target:
                while chunk := response.read(1024 * 1024):
                    target.write(chunk)
        if file_sha256(temporary) != EXPECTED_SHA256:
            raise ValueError("Downloaded Hetionet checksum does not match the pinned release")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def qualified_id(kind: str, identifier: str | int) -> str:
    """Preserve the source namespace to prevent cross-type ID collisions."""
    return f"{kind}::{identifier}"


def sources_for(properties: dict) -> list[str]:
    """Normalize available source names without inventing missing provenance."""
    sources = properties.get("sources", properties.get("source", []))
    if isinstance(sources, str):
        return [sources]
    return sorted(str(source) for source in sources) if sources else []


def normalize_edge(record: dict, relation: str) -> dict:
    """Retain exact upstream metadata on an edge with a stable content identity."""
    source = qualified_id(*record["source_id"])
    target = qualified_id(*record["target_id"])
    identity = f"{source}|{relation}|{target}"
    properties = record.get("data", {})
    return {
        "id": "e_" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        "source": source,
        "target": target,
        "type": relation,
        "direction": record.get("direction", "both"),
        "sources": sources_for(properties),
        "license": properties.get("license"),
        "data": properties,
    }


def json_default(value):
    """Represent ijson decimal values as ordinary JSON numbers."""
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def write_json(path: Path, value: dict, *, pretty: bool = False) -> None:
    """Write a complete JSON artifact atomically."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            value,
            default=json_default,
            indent=2 if pretty else None,
            separators=None if pretty else (",", ":"),
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def prepare(raw_path: Path, output: Path) -> dict:
    """Extract the four-type evidence graph and a separate treatment label set."""
    checksum = file_sha256(raw_path)
    if checksum != EXPECTED_SHA256:
        raise ValueError("Hetionet checksum mismatch; no processed artifacts were written")
    nodes = []
    with bz2.open(raw_path, "rb") as source:
        for node in ijson.items(source, "nodes.item"):
            if node["kind"] not in LABELS:
                continue
            properties = node.get("data", {})
            nodes.append(
                {
                    "id": qualified_id(node["kind"], node["identifier"]),
                    "identifier": str(node["identifier"]),
                    "name": node["name"],
                    "label": node["kind"],
                    "url": properties.get("url"),
                    "data": properties,
                }
            )
    node_ids = {node["id"] for node in nodes}
    evidence, treatments = [], []
    discarded_self_loops = 0
    with bz2.open(raw_path, "rb") as source:
        for edge in ijson.items(source, "edges.item"):
            signature = (edge["source_id"][0], edge["kind"], edge["target_id"][0])
            relation = RELATIONSHIPS.get(signature)
            if signature == ("Compound", "treats", "Disease"):
                treatments.append(normalize_edge(edge, "TREATS"))
            elif relation:
                normalized = normalize_edge(edge, relation)
                if normalized["source"] == normalized["target"]:
                    discarded_self_loops += 1
                    continue
                if normalized["source"] not in node_ids or normalized["target"] not in node_ids:
                    raise ValueError("A retained relationship references a missing node")
                evidence.append(normalized)
    nodes.sort(key=lambda node: node["id"])
    evidence.sort(key=lambda edge: edge["id"])
    treatments.sort(key=lambda edge: edge["id"])
    if len(nodes) != EXPECTED_NODE_COUNT or len(treatments) != EXPECTED_TREATMENT_COUNT:
        raise ValueError("Unexpected pinned dataset counts; extraction is incomplete")
    node_counts = dict(Counter(node["label"] for node in nodes))
    edge_counts = dict(Counter(edge["type"] for edge in evidence))
    manifest = {
        "dataset": "Hetionet",
        "version": "1.0",
        "upstream_commit": UPSTREAM_COMMIT,
        "url": DATASET_URL,
        "dataset_sha256": checksum,
        "compressed_bytes": raw_path.stat().st_size,
        "nodes": len(nodes),
        "edges": len(evidence),
        "node_counts": node_counts,
        "edge_counts": edge_counts,
        "treatment_labels": len(treatments),
        "discarded_self_loops": discarded_self_loops,
        "evidence_relationships": sorted(RELATIONSHIPS.values()),
        "excluded_from_features": ["TREATS", "PALLIATES"],
        "citation": {
            "title": (
                "Systematic integration of biomedical knowledge prioritizes drugs for repurposing"
            ),
            "authors": "Himmelstein et al.",
            "year": 2017,
            "doi": "https://doi.org/10.7554/eLife.26726",
            "repository": "https://github.com/hetio/hetionet",
        },
        "license_policy": (
            "Original Hetionet repository content is CC0; constituent resources retain "
            "their own terms. Node and edge metadata preserve available source/license "
            "attributes. A missing license or primary citation is not an open-license claim."
        ),
        "provenance_policy": (
            "Source names and metadata are imported unchanged, except source lists are "
            "normalized for presentation. Consolidated relations are not independent studies."
        ),
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(
        output / "graph.json",
        {
            "nodes": nodes,
            "edges": evidence,
            "treatments": treatments,
            "metadata": manifest,
        },
    )
    manifest["graph_sha256"] = file_sha256(output / "graph.json")
    write_json(output / "manifest.json", manifest, pretty=True)
    return manifest


def main() -> None:
    """Run the reproducible ingestion command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path("data/raw/hetionet-v1.0.json.bz2"))
    parser.add_argument("--output", type=Path, default=Path("data/processed"))
    parser.add_argument("--download", action="store_true", help="Re-download the pinned dataset")
    args = parser.parse_args()
    if args.download or not args.raw.exists():
        download_dataset(args.raw)
    print(json.dumps(prepare(args.raw, args.output), indent=2))


if __name__ == "__main__":
    main()
