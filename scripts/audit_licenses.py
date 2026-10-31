"""Inventory preserved source/license metadata without deciding legal permission.

The output describes the exact prepared graph bytes. A marker identifies text
that warrants review; it does not determine which rights apply to a proposed use.
No network requests, source mutation, model training or automatic relicensing occur.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from app import __version__

COLLECTIONS = ("nodes", "edges", "treatments")
LICENSE_MARKERS = {
    "CC0 1.0": {
        "markers": ["public_domain_dedication_text"],
        "reference": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
    "CC BY 3.0": {
        "markers": ["attribution_text"],
        "reference": "https://creativecommons.org/licenses/by/3.0/",
    },
    "CC BY 4.0": {
        "markers": ["attribution_text"],
        "reference": "https://creativecommons.org/licenses/by/4.0/",
    },
    "CC BY-NC 4.0": {
        "markers": ["attribution_text", "noncommercial_text"],
        "reference": "https://creativecommons.org/licenses/by-nc/4.0/",
    },
    "CC BY-SA 3.0": {
        "markers": ["attribution_text", "share_alike_text"],
        "reference": "https://creativecommons.org/licenses/by-sa/3.0/",
    },
    "ODbL 1.0": {
        "markers": ["attribution_text", "share_alike_text", "database_license_text"],
        "reference": "https://opendatacommons.org/licenses/odbl/1-0/",
    },
}


def _text_values(value: object, field: str) -> set[str]:
    """Accept scalar/list metadata; reject malformed values rather than omit them."""
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return {item.strip() for item in value if item.strip()}
    raise ValueError(f"Expected text or a text list in {field}")


def _record_metadata(record: dict, collection: str) -> tuple[list[str], list[str], list[str]]:
    """Preserve distinct declarations; never treat an edge endpoint as a publisher."""
    data = record.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("Record data must be an object")
    licenses = _text_values(record.get("license"), "license") | _text_values(
        data.get("license"), "data.license"
    )
    sources = (
        _text_values(record.get("sources"), "sources")
        | _text_values(data.get("sources"), "data.sources")
        | _text_values(data.get("source"), "data.source")
    )
    if collection == "nodes":
        sources |= _text_values(record.get("source"), "source")
    flags = set()
    for value in licenses:
        flags.update(
            LICENSE_MARKERS.get(value, {"markers": ["unrecognized_license_text"]})["markers"]
        )
    if not licenses:
        flags.add("missing_license_metadata")
    if len(licenses) > 1:
        flags.add("multiple_license_declarations")
    if not sources:
        flags.add("missing_source_metadata")
    return sorted(licenses), sorted(sources), sorted(flags)


def _empty_counts() -> dict:
    return {
        "records": 0,
        "licenses": Counter(),
        "review_flags": Counter(),
        "missing_license_records": 0,
        "missing_source_records": 0,
    }


def _count_record(bucket: dict, licenses: list[str], sources: list[str], flags: list[str]) -> None:
    bucket["records"] += 1
    bucket["licenses"].update(licenses)
    bucket["review_flags"].update(flags)
    bucket["missing_license_records"] += not licenses
    bucket["missing_source_records"] += not sources


def _plain_counts(bucket: dict) -> dict:
    return {
        key: dict(sorted(value.items())) if isinstance(value, Counter) else value
        for key, value in bucket.items()
    }


def inventory(graph: dict, graph_sha256: str) -> dict:
    """Count actual declarations once per record and retain per-source co-occurrence.

    An edge mentioning several sources contributes once to the collection totals
    and once to each source inventory. Its license is not attributed separately
    to every publisher: the source table records co-occurrence, not source terms.
    """
    collection_counts = {}
    type_counts = {}
    source_counts = defaultdict(_empty_counts)
    source_collections = defaultdict(Counter)
    source_examples = defaultdict(set)
    total = _empty_counts()
    for collection in COLLECTIONS:
        records = graph.get(collection)
        if not isinstance(records, list):
            raise ValueError(f"Prepared graph must contain a {collection} list")
        bucket = _empty_counts()
        for record in records:
            if not isinstance(record, dict) or not isinstance(record.get("id"), str):
                raise ValueError("Every inventory record requires a text id")
            licenses, sources, flags = _record_metadata(record, collection)
            category = str(record.get("label" if collection == "nodes" else "type", "unknown"))
            category_key = f"{collection}:{category}"
            category_bucket = type_counts.setdefault(category_key, _empty_counts())
            for target in (bucket, category_bucket, total):
                _count_record(target, licenses, sources, flags)
            for source in sources:
                _count_record(source_counts[source], licenses, sources, flags)
                source_collections[source][collection] += 1
                source_examples[source].add((collection, category, record["id"]))
        collection_counts[collection] = _plain_counts(bucket)
    metadata = graph.get("metadata", {})
    return {
        "schema_version": "1.0",
        "application_version": __version__,
        "input": {
            "graph_sha256": graph_sha256,
            "dataset": metadata.get("dataset"),
            "version": metadata.get("version"),
            "dataset_sha256": metadata.get("dataset_sha256"),
            "upstream_commit": metadata.get("upstream_commit"),
        },
        "scope": {
            "collections": list(COLLECTIONS),
            "count_unit": "One retained node, evidence edge, or separate treatment-label record",
            "license_unit": "Distinct nonempty declaration per record, not a legal conclusion",
            "source_unit": (
                "Source/record co-occurrence; multisource records are counted for each source"
            ),
            "source_license_caveat": (
                "A consolidated edge license is not assigned as the license of every named source. "
                "Inspect upstream terms and the original record before making a use decision."
            ),
            "missing_metadata": "Missing text is not permission; unknown text remains unknown",
        },
        "legal_clearance": {
            "status": "not_assessed",
            "commercial_permission": None,
            "reason": (
                "This inventory records supplied metadata only. It does not determine rights, "
                "license compatibility, contractual permission, exceptions, or "
                "commercial eligibility. "
                "The MIT source-code license does not relicense constituent data."
            ),
        },
        "summary": _plain_counts(total),
        "collections": collection_counts,
        "record_types": {key: _plain_counts(value) for key, value in sorted(type_counts.items())},
        "license_markers": LICENSE_MARKERS,
        "sources": [
            {
                "name": source,
                **_plain_counts(source_counts[source]),
                "collections": dict(sorted(source_collections[source].items())),
                "examples": [
                    {"collection": collection, "type": category, "id": identifier}
                    for collection, category, identifier in sorted(source_examples[source])[:3]
                ],
            }
            for source in sorted(source_counts)
        ],
    }


def audit_file(graph_path: Path, output: Path) -> dict:
    """Bind the inventory to input bytes and write deterministic review evidence."""
    if graph_path.resolve() == output.resolve() or (
        output.exists() and graph_path.exists() and output.samefile(graph_path)
    ):
        raise ValueError("Inventory output must not overwrite the source graph")
    raw = graph_path.read_bytes()
    report = inventory(json.loads(raw), hashlib.sha256(raw).hexdigest())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    """Generate an inventory; successful execution means counted, never cleared."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, default=Path("data/processed/graph.json"))
    parser.add_argument(
        "--output", type=Path, default=Path("reports/v1.2.0/license-inventory.json")
    )
    arguments = parser.parse_args()
    report = audit_file(arguments.graph, arguments.output)
    print(
        f"Inventoried {report['summary']['records']} records from "
        f"{report['input']['graph_sha256']}; legal clearance: not assessed. "
        f"Report: {arguments.output}"
    )


if __name__ == "__main__":
    main()
