"""Release archives must come from committed source and a matching complete snapshot."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import zipfile

import pytest

from infra import package_release as package


def write_json(path, value):
    """Write fixture JSON with stable bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True))


@pytest.fixture
def release_input(tmp_path):
    """Create a genuine local Git history and a separately generated tiny snapshot."""
    repo = tmp_path / "source"
    repo.mkdir()
    files = {
        "app/__init__.py": '__version__ = "1.3.0"\n',
        "pyproject.toml": '[project]\nversion = "1.3.0"\n',
        "LICENSE": "Explicit test fixture license\n",
        "docs/provenance_audit.md": "Test fixture documentation\n",
        "frontend/assets/mark.svg": '<svg xmlns="http://www.w3.org/2000/svg"><title>Committed mark</title></svg>\n',
        "reports/v1.3.0/provenance-review-marimastat.html": "<!doctype html><title>Committed review</title>\n",
        "executable.sh": "#!/bin/sh\nexit 0\n",
    }
    for name in package.RUNTIME_FILES:
        files["frontend/" + name] = "committed runtime: " + name
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    (repo / "executable.sh").chmod(0o755)
    write_json(
        repo / "data/processed/manifest.json",
        {"dataset_sha256": "a" * 64, "graph_sha256": "b" * 64},
    )
    model = {"name": "Packaging identity fixture"}
    model_sha256 = sha256(json.dumps(model, sort_keys=True).encode()).hexdigest()
    write_json(repo / "data/processed/model.json", {**model, "model_sha256": model_sha256})
    write_json(
        repo / "demo.ipynb",
        {
            "cells": [
                {
                    "cell_type": "code",
                    "source": ["print(1)"],
                    "execution_count": 1,
                    "outputs": [{"output_type": "stream", "text": ["1\n"]}],
                }
            ]
        },
    )
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Release fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-qm",
            "Explicit packaging fixture",
        ],
        check=True,
    )
    snapshot = tmp_path / "snapshot"
    write_json(snapshot / "cases/example.json", {"case": "fixture"})
    raw = (snapshot / "cases/example.json").read_bytes()
    manifest = {
        "mode": "snapshot",
        "health": {"version": "1.3.0"},
        "dataset_sha256": "a" * 64,
        "graph_sha256": "b" * 64,
        "model_sha256": model_sha256,
        "file_count": 1,
        "files": [
            {"path": "cases/example.json", "bytes": len(raw), "sha256": sha256(raw).hexdigest()}
        ],
    }
    write_json(snapshot / "manifest.json", manifest)
    return repo, snapshot, tmp_path


def test_archives_are_repeatable_and_use_immutable_source_blobs(release_input):
    """Dirty source cannot leak into the release; ZIP metadata preserves executable mode."""
    repo, snapshot, root = release_input
    (repo / "frontend/index.html").write_text("uncommitted content must not ship")
    first = package.build(repo, "HEAD", snapshot, root / "first")
    second = package.build(repo, "HEAD", snapshot, root / "second")
    assert first == second
    assert first["application_version"] == "1.3.0"
    for path in (root / "first").iterdir():
        assert path.read_bytes() == (root / "second" / path.name).read_bytes()
    with zipfile.ZipFile(root / "first/ariadne-research-edition.zip") as archive:
        assert archive.read("index.html") == b"committed runtime: index.html"
        assert (
            archive.read("data/cases/example.json")
            == (snapshot / "cases/example.json").read_bytes()
        )
    with zipfile.ZipFile(root / "first/ariadne-v1.3.0-source.zip") as archive:
        assert archive.getinfo("ariadne-bio-v1.3.0/executable.sh").external_attr >> 16 == 0o100755
    sums = (root / "first/SHA256SUMS").read_text().splitlines()
    assert {line.split("  ")[1] for line in sums} == {
        path.name for path in (root / "first").iterdir()
    } - {"SHA256SUMS"}
    for line in sums:
        digest, name = line.split("  ")
        assert sha256((root / "first" / name).read_bytes()).hexdigest() == digest


def test_committed_assets_and_html_reviews_survive_dirty_working_tree(release_input):
    """The complete research UI and review example use exact committed dependency bytes."""
    repo, snapshot, root = release_input
    asset = repo / "frontend/assets/mark.svg"
    review = repo / "reports/v1.3.0/provenance-review-marimastat.html"
    expected_asset, expected_review = asset.read_bytes(), review.read_bytes()
    asset.write_text("uncommitted asset must not override the released mark")
    review.write_text("uncommitted report must not override the released review")
    package.build(repo, "HEAD", snapshot, root / "output")
    with zipfile.ZipFile(root / "output/ariadne-research-edition.zip") as archive:
        assert archive.read("assets/mark.svg") == expected_asset
        assert archive.read("reports/v1.3.0/provenance-review-marimastat.html") == expected_review


@pytest.mark.parametrize("key", ["model_sha256", "graph_sha256", "dataset_sha256"])
def test_mixed_snapshot_identity_is_rejected_without_output(release_input, key):
    """A fresh runtime cannot package stale scientific records as a matching snapshot."""
    repo, snapshot, root = release_input
    manifest = json.loads((snapshot / "manifest.json").read_text())
    manifest[key] = "d" * 64
    write_json(snapshot / "manifest.json", manifest)
    with pytest.raises(ValueError, match="identity"):
        package.build(repo, "HEAD", snapshot, root / "output")
    assert not (root / "output").exists()


def test_source_model_cannot_retain_an_old_identity_after_parameter_change(release_input):
    """Matching declared identities cannot disguise different actual model bytes."""
    repo, snapshot, _ = release_input
    source, files = package.read_source(repo, "HEAD")
    model = json.loads(files["data/processed/model.json"])
    model["name"] = "A changed parameter payload retaining the old hash"
    files["data/processed/model.json"] = json.dumps(model).encode()
    with pytest.raises(ValueError, match="model checksum"):
        package.read_snapshot(snapshot, source, files)


def test_case_corruption_or_extra_file_is_rejected(release_input):
    """Manifest integrity covers raw bytes and the complete data directory."""
    repo, snapshot, root = release_input
    case = snapshot / "cases/example.json"
    original = case.read_bytes()
    case.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="checksum mismatch"):
        package.build(repo, "HEAD", snapshot, root / "output")
    case.write_bytes(original)
    (snapshot / "unlisted.json").write_text("{}")
    with pytest.raises(ValueError, match="outside its complete manifest"):
        package.build(repo, "HEAD", snapshot, root / "output")
    assert not (root / "output").exists()


def test_snapshot_symlink_and_existing_output_are_preserved(release_input):
    """Packaging never follows an input escape or replaces an existing deliverable."""
    repo, snapshot, root = release_input
    output = root / "output"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="existing artifacts are preserved"):
        package.build(repo, "HEAD", snapshot, output)
    assert (output / "keep.txt").read_text() == "keep"
    case = snapshot / "cases/example.json"
    external = root / "external.json"
    external.write_bytes(case.read_bytes())
    case.unlink()
    case.symlink_to(external)
    with pytest.raises(ValueError, match="Symlinks"):
        package.build(repo, "HEAD", snapshot, root / "other")


@pytest.mark.parametrize(
    "name", ["../secret", "/tmp/secret", "a\\b", ".env", "x/.aws/key", "x/../y", "x//y"]
)
def test_unsafe_archive_paths_are_rejected(name):
    """Input-controlled member names cannot escape an archive or include secret locations."""
    with pytest.raises(ValueError, match="Unsafe release path"):
        package.safe_path(name)


def test_unexecuted_or_error_notebook_is_not_presented_as_executed():
    """Retained notebook outputs are a required artifact, not a fabricated execution result."""
    cell = {
        "cell_type": "code",
        "source": ["raise ValueError()"],
        "execution_count": None,
        "outputs": [],
    }
    with pytest.raises(ValueError, match="execution count"):
        package.recorded_notebook(json.dumps({"cells": [cell]}).encode())
    cell.update(execution_count=1, outputs=[{"output_type": "error"}])
    with pytest.raises(ValueError, match="execution error"):
        package.recorded_notebook(json.dumps({"cells": [cell]}).encode())


def test_curated_evidence_keeps_input_checksums_and_declares_verification_boundary(release_input):
    """Bundling a report preserves it; the packager does not certify the report's claims."""
    repo, snapshot, root = release_input
    evidence = root / "evidence"
    evidence.mkdir()
    content = b'{"status":"fixture only, not a CI result"}'
    (evidence / "result.json").write_bytes(content)
    checksum = f"{sha256(content).hexdigest()}  result.json\n"
    (evidence / "SHA256SUMS").write_text(checksum)
    report = package.build(repo, "HEAD", snapshot, root / "output", evidence)
    assert "not independently authenticated" in report["verification_scope"]
    with zipfile.ZipFile(root / "output/ariadne-v1.3.0-verification.zip") as archive:
        assert archive.read("INPUT-SHA256SUMS").decode() == checksum
        assert archive.read("result.json") == content
        sums = archive.read("SHA256SUMS").decode().splitlines()
        assert {line.split("  ")[1] for line in sums} == set(archive.namelist()) - {"SHA256SUMS"}
        for line in sums:
            digest, name = line.split("  ")
            assert sha256(archive.read(name)).hexdigest() == digest
    (evidence / "extra.json").write_text("{}")
    with pytest.raises(ValueError, match="every payload exactly"):
        package.read_evidence(evidence)
