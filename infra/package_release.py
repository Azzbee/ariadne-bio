"""Package one explicit Git revision and its matching recorded research snapshot.

This checks source/snapshot identities, deterministic archives and payload hashes.
It does not infer that CI passed, execute a certificate verifier, authenticate a
publisher or grant data rights. External verification evidence is a separate input.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import io
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile

RUNTIME_FILES = (
    "index.html",
    "styles.css",
    "config.js",
    "app.js",
    "api.js",
    "graph.js",
    "utils.js",
    "investigation.js",
    "audit.js",
    "audit-model.js",
    "audit.css",
    "integrity.js",
    "provenance.js",
    "provenance-model.js",
    "provenance.css",
)
SECRET_PARTS = {".git", ".aws", ".ssh", "node_modules", ".venv", "credentials"}


def safe_path(name: str) -> str:
    """Accept a normalized relative POSIX archive path, excluding secret locations."""
    path = PurePosixPath(name)
    if not name or "\\" in name or any(ord(char) < 32 for char in name) or path.is_absolute():
        raise ValueError(f"Unsafe release path: {name!r}")
    if (
        any(part in {"", ".", ".."} for part in name.split("/"))
        or any(part in SECRET_PARTS for part in path.parts)
        or any(part.startswith(".env") and part != ".env.example" for part in path.parts)
    ):
        raise ValueError(f"Unsafe release path: {name!r}")
    return name


def _json(value: dict) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def _entry(name: str, content: bytes) -> dict:
    return {"path": name, "bytes": len(content), "sha256": sha256(content).hexdigest()}


def read_source(repo: Path, ref: str) -> tuple[dict, dict[str, bytes]]:
    """Read only immutable Git blobs; working-tree modifications cannot enter assets."""

    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    commit = git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()
    tree = git("rev-parse", commit + "^{tree}").decode().strip()
    records = git("ls-tree", "-rz", "--full-tree", commit).split(b"\x00")
    files = {}
    inventory = []
    for record in filter(None, records):
        header, raw_name = record.split(b"\t", 1)
        mode, kind, blob = header.decode().split()
        name = safe_path(raw_name.decode("utf-8"))
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError(f"Unsupported source entry: {name} ({mode} {kind})")
        content = git("cat-file", "blob", blob)
        files[name] = content
        inventory.append({**_entry(name, content), "git_mode": mode, "git_blob": blob})
    version_match = re.search(
        rb'__version__ = "([0-9]+\.[0-9]+\.[0-9]+)"', files["app/__init__.py"]
    )
    if version_match is None:
        raise ValueError("Committed source must declare a semantic application version")
    version = version_match.group(1).decode()
    if f'version = "{version}"'.encode() not in files["pyproject.toml"]:
        raise ValueError("Committed package and application versions disagree")
    return {"commit": commit, "tree": tree, "version": version, "files": inventory}, files


def _read_plain_file(root: Path, relative: str) -> bytes:
    safe_path(relative)
    candidate = root / relative
    if any(part.is_symlink() for part in [candidate, *candidate.parents] if part != root.parent):
        raise ValueError(f"Symlinks are not permitted in release inputs: {relative}")
    if not candidate.resolve().is_relative_to(root.resolve()) or not candidate.is_file():
        raise ValueError(f"Missing or escaped release input: {relative}")
    return candidate.read_bytes()


def read_snapshot(directory: Path, source: dict, files: dict[str, bytes]) -> tuple[dict, dict]:
    """Bind every recorded case byte to its manifest and immutable source identities."""
    manifest_bytes = _read_plain_file(directory, "manifest.json")
    manifest = json.loads(manifest_bytes)
    if (
        manifest.get("mode") != "snapshot"
        or manifest.get("health", {}).get("version") != source["version"]
    ):
        raise ValueError("Snapshot mode/version does not match committed source")
    graph = json.loads(files["data/processed/manifest.json"])
    model = json.loads(files["data/processed/model.json"])
    unsigned_model = {key: value for key, value in model.items() if key != "model_sha256"}
    expected_model = sha256(json.dumps(unsigned_model, sort_keys=True).encode()).hexdigest()
    if model.get("model_sha256", expected_model) != expected_model:
        raise ValueError("Committed model checksum does not match its actual parameters")
    expected = {
        "dataset_sha256": graph["dataset_sha256"],
        "graph_sha256": graph["graph_sha256"],
        "model_sha256": expected_model,
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Snapshot graph/model identity does not match committed artifacts")
    contents = {"data/manifest.json": manifest_bytes}
    recorded = manifest.get("files", [])
    if not recorded or manifest.get("file_count") != len(recorded):
        raise ValueError("Snapshot file inventory is incomplete")
    names = set()
    for item in recorded:
        name = safe_path(item["path"])
        if name in names or name == "manifest.json" or not name.endswith(".json"):
            raise ValueError("Snapshot paths must be unique case JSON files")
        names.add(name)
        content = _read_plain_file(directory, name)
        if _entry(name, content) != item:
            raise ValueError(f"Snapshot byte count/checksum mismatch: {name}")
        json.loads(content)
        contents["data/" + name] = content
    actual = {
        str(path.relative_to(directory)).replace("\\", "/")
        for path in directory.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if actual != names | {"manifest.json"}:
        raise ValueError("Snapshot contains files outside its complete manifest")
    return {**expected, "case_files": len(recorded)}, contents


def recorded_notebook(content: bytes) -> dict:
    """Require retained outputs for every committed nonempty code cell, without fabrication."""
    notebook = json.loads(content)
    cells = [
        cell
        for cell in notebook["cells"]
        if cell["cell_type"] == "code" and "".join(cell["source"]).strip()
    ]
    if not cells or any(cell.get("execution_count") is None for cell in cells):
        raise ValueError("Every committed nonempty notebook code cell must have an execution count")
    if any(
        output.get("output_type") == "error" for cell in cells for output in cell.get("outputs", [])
    ):
        raise ValueError("Committed notebook contains an execution error")
    return {
        "recorded_code_cells": len(cells),
        "interpretation": (
            "Recorded outputs; actual execution is established by separate CI evidence."
        ),
    }


def zip_bytes(files: dict[str, bytes], modes: dict[str, int] | None = None) -> bytes:
    """Use sorted paths, fixed metadata and full extraction verification."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(files.items()):
            info = zipfile.ZipInfo(safe_path(name), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (modes or {}).get(name, 0o100644) << 16
            archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    value = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(value)) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(files):
            raise ValueError("Packaged ZIP failed CRC/inventory validation")
        if any(archive.read(name) != content for name, content in files.items()):
            raise ValueError("Packaged ZIP does not contain its declared source bytes")
    return value


def read_evidence(directory: Path) -> dict[str, bytes]:
    """Require a curated, completely checksummed evidence directory; never infer CI truth."""
    checksums = _read_plain_file(directory, "SHA256SUMS").decode()
    files = {"SHA256SUMS": checksums.encode()}
    for line in checksums.splitlines():
        digest, separator, name = line.partition("  ")
        if not separator or not re.fullmatch(r"[0-9a-f]{64}", digest) or name in files:
            raise ValueError("Invalid or duplicate evidence checksum entry")
        content = _read_plain_file(directory, safe_path(name))
        if sha256(content).hexdigest() != digest:
            raise ValueError(f"Evidence checksum mismatch: {name}")
        files[name] = content
    actual = {
        str(path.relative_to(directory))
        for path in directory.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if set(files) != actual or len(files) == 1:
        raise ValueError("Evidence SHA256SUMS must cover every payload exactly")
    return files


def build(repo: Path, ref: str, snapshot: Path, output: Path, evidence: Path | None = None) -> dict:
    """Validate all inputs before atomically publishing a new release directory."""
    if output.is_symlink() or (output.exists() and (not output.is_dir() or any(output.iterdir()))):
        raise ValueError("Release output must be absent or empty; existing artifacts are preserved")
    source, files = read_source(repo, ref)
    version = source["version"]
    notebook = recorded_notebook(files["demo.ipynb"])
    identity, snapshot_files = read_snapshot(snapshot, source, files)
    provenance = _json(
        {
            "application_version": version,
            **{key: source[key] for key in ("commit", "tree")},
            **identity,
        }
    )
    research = {name: files["frontend/" + name] for name in RUNTIME_FILES}
    research.update(snapshot_files)
    research.update({name: content for name, content in files.items() if name.startswith("docs/")})
    research.update(
        {
            name: content
            for name, content in files.items()
            if name.startswith("reports/") and name.endswith((".json", ".jpg", ".png"))
        }
    )
    for name in ("manifest.json", "model.json", "evaluation.json"):
        path = "data/processed/" + name
        if path in files:
            research[path] = files[path]
    research["LICENSE"] = files["LICENSE"]
    research["SOURCE-REVISION.json"] = provenance
    research["README.md"] = (
        f"# ARIADNE {version} recorded research edition\n\n"
        "Run `python3 -m http.server 8080 --bind 127.0.0.1` here and open "
        "http://localhost:8080. This edition uses recorded results; it runs no live "
        "database, model provider, audit optimizer or witness replay.\n\n"
        "Code is MIT; constituent data retain their own terms, including noncommercial "
        "and missing metadata. See docs/data_sources.md and docs/licensing_audit.md. "
        "A package hash is not a signature or data-rights clearance.\n\n"
        f"Source commit: `{source['commit']}`. Exact Git tree: `{source['tree']}`.\n\n"
        "For offline certificate replay, extract the separate source ZIP, run "
        "`make install`, then `.venv/bin/python -m scripts.prepare_data` to prepare "
        "the graph while retaining the supplied fitted model. Run "
        "`.venv/bin/python -m scripts.verify_audit certificate.json --data-dir data/processed`. "
        "`make data` deliberately retrains and may change model identity.\n"
    ).encode()
    source_files = {f"ariadne-bio-v{version}/{name}": content for name, content in files.items()}
    source_modes = {
        f"ariadne-bio-v{version}/{item['path']}": int(item["git_mode"], 8)
        for item in source["files"]
    }
    assets = {
        "ariadne-research-edition.zip": zip_bytes(research),
        f"ariadne-v{version}-source.zip": zip_bytes(source_files, source_modes),
        f"ariadne-v{version}-executed.ipynb": files["demo.ipynb"],
    }
    evidence_inventory = None
    if evidence is not None:
        evidence_files = read_evidence(evidence)
        evidence_inventory = [
            _entry(name, content) for name, content in sorted(evidence_files.items())
        ]
        if "SOURCE-REVISION.json" in evidence_files or "INPUT-SHA256SUMS" in evidence_files:
            raise ValueError("Evidence uses a reserved packaging metadata filename")
        evidence_files["INPUT-SHA256SUMS"] = evidence_files.pop("SHA256SUMS")
        evidence_files["SOURCE-REVISION.json"] = provenance
        evidence_files["SHA256SUMS"] = "".join(
            f"{sha256(content).hexdigest()}  {name}\n"
            for name, content in sorted(evidence_files.items())
        ).encode()
        assets[f"ariadne-v{version}-verification.zip"] = zip_bytes(evidence_files)
    manifest = {
        "schema_version": "1.0",
        "application_version": version,
        "source": source,
        "snapshot": identity,
        "notebook": notebook,
        "assets": [_entry(name, content) for name, content in sorted(assets.items())],
        "evidence_files": evidence_inventory,
        "verification_scope": (
            "Immutable source blobs, version/graph/model matching, complete raw snapshot "
            "checksums, recorded notebook outputs, deterministic ZIP inventories/CRC and "
            "payload bytes. Supplied CI evidence is preserved, not independently authenticated "
            "or interpreted as a passing run by this packager."
        ),
    }
    assets["release-manifest.json"] = _json(manifest)
    assets["SHA256SUMS"] = "".join(
        f"{sha256(content).hexdigest()}  {name}\n" for name, content in sorted(assets.items())
    ).encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".ariadne-release-", dir=output.parent))
    try:
        for name, content in assets.items():
            (stage / name).write_bytes(content)
        stage.replace(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def main() -> None:
    """Expose a version-independent, source-bound release command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--ref", required=True)
    parser.add_argument("--snapshot", type=Path, default=Path("frontend/data"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args()
    report = build(args.repo, args.ref, args.snapshot, args.output, args.evidence_dir)
    print(
        json.dumps(
            {
                "source_commit": report["source"]["commit"],
                "version": report["application_version"],
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
