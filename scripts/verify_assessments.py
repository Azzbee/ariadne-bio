"""Compare every score with the actual v1.0.0 implementation without refitting.

Run ``python -m scripts.verify_assessments`` after preparing the pinned dataset.
The local Git object database must contain the v1.0.0 source commit. Shallow
clones must fetch history containing that release before running this command.
No network fetch, model fitting or modification of scientific inputs is performed.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

import numpy as np

from app import __version__
from app.graph_engine import GraphEngine
from scripts.export_snapshot import exclusion_combinations
from scripts.prepare_data import write_json

BASELINE_REVISION = "27f735ae9d0487ffd8c1fc3c740c2a7f99910893"
BASELINE_SOURCE_SHA256 = "014064fcede6d8c698f5b60c496e0dbea328bf9a701dc2d2ed607b32a9fcfe10"
EXAMPLE_COMPOUNDS = {
    "nicotine": "Compound::DB00184",
    "galantamine": "Compound::DB00674",
}
EXAMPLE_DISEASE = "Disease::DOID:10652"
ROOT = Path(__file__).resolve().parents[1]


def file_sha256(path: Path) -> str:
    """Hash actual artifact bytes without reserializing their JSON contents."""
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def load_baseline(data_dir: Path):
    """Import only the checksum-verified source from the immutable release commit."""
    try:
        source = subprocess.check_output(
            ["git", "show", f"{BASELINE_REVISION}:app/graph_engine.py"],
            cwd=ROOT,
            stderr=subprocess.PIPE,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            "Score verification requires Git and the local v1.0.0 commit "
            f"{BASELINE_REVISION}. Fetch the repository history before retrying."
        ) from error
    if hashlib.sha256(source).hexdigest() != BASELINE_SOURCE_SHA256:
        raise RuntimeError("The historical engine source does not match its pinned checksum")
    with tempfile.TemporaryDirectory(prefix="ariadne-score-baseline-") as directory:
        path = Path(directory) / "graph_engine.py"
        path.write_bytes(source)
        specification = importlib.util.spec_from_file_location("ariadne_v1_0_reference", path)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        return module.GraphEngine(data_dir)


def compare_scores(baseline, current: GraphEngine) -> dict:
    """Measure every scalar score, including unsupported pairs, with no tolerance."""
    if baseline.entities != current.entities:
        raise ValueError("Historical and current score matrices use different entity orders")
    scenarios = []
    for excluded in exclusion_combinations():
        before, after = baseline.score_matrix(excluded), current.score_matrix(excluded)
        if before.shape != after.shape:
            raise ValueError("Historical and current score matrices have different shapes")
        finite = bool(np.isfinite(before).all() and np.isfinite(after).all())
        unequal = int(np.count_nonzero(before != after))
        scenarios.append(
            {
                "excluded": list(excluded),
                "shape": list(before.shape),
                "compared_scores": int(before.size),
                "unequal_scores": unequal,
                "all_finite": finite,
                "max_absolute_difference": (
                    float(np.max(np.abs(before - after))) if finite else None
                ),
                "baseline_scores_sha256": hashlib.sha256(
                    np.asarray(before, dtype="<f8").tobytes(order="C")
                ).hexdigest(),
                "current_scores_sha256": hashlib.sha256(
                    np.asarray(after, dtype="<f8").tobytes(order="C")
                ).hexdigest(),
            }
        )
    all_finite = all(row["all_finite"] for row in scenarios)
    return {
        "status": (
            "passed"
            if all_finite
            and all(
                row["baseline_scores_sha256"] == row["current_scores_sha256"] for row in scenarios
            )
            else "failed"
        ),
        "comparison": (
            "Exact float64 bytes, no numerical tolerance; all pairs including unsupported ones"
        ),
        "array_hash_encoding": "Little-endian IEEE-754 float64, row-major compound/disease order",
        "exclusion_configurations": len(scenarios),
        "compared_scores": sum(row["compared_scores"] for row in scenarios),
        "unequal_scores": sum(row["unequal_scores"] for row in scenarios),
        "all_finite": all_finite,
        "max_absolute_difference": (
            max(row["max_absolute_difference"] for row in scenarios) if all_finite else None
        ),
        "scenarios": scenarios,
    }


def save_examples(engine: GraphEngine, output: Path) -> list[dict]:
    """Save complete selected-pair arithmetic and a compact measured comparison."""
    examples = []
    for name, compound_id in EXAMPLE_COMPOUNDS.items():
        assessment = engine.assessment(EXAMPLE_DISEASE, compound_id, ["INTERACTS"])
        path = output / f"assessment-{name}-interacts.json"
        write_json(path, assessment, pretty=True)
        examples.append(
            {
                "disease": assessment["disease"],
                "compound": assessment["compound"],
                "excluded": assessment["excluded"],
                "baseline": assessment["baseline"],
                "current": assessment["current"],
                "delta": assessment["delta"],
                "rank_unchanged": assessment["baseline"]["rank"] == assessment["current"]["rank"],
                "assessment_file": path.name,
                "assessment_sha256": file_sha256(path),
            }
        )
    return examples


def verify(data_dir: Path, output: Path) -> dict:
    """Bind observed score equality and examples to the exact input and source bytes."""
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "score-regression.json"
    started = datetime.now(timezone.utc).isoformat()
    write_json(report_path, {"status": "started", "started_at_utc": started}, pretty=True)
    for name in EXAMPLE_COMPOUNDS:
        (output / f"assessment-{name}-interacts.json").unlink(missing_ok=True)
    try:
        baseline = load_baseline(data_dir)
        engine = GraphEngine(data_dir)
        result = compare_scores(baseline, engine)
        report = {
            "schema_version": "1.0",
            "started_at_utc": started,
            "application_version": __version__,
            "reproduce": (
                "python -m scripts.verify_assessments --data-dir data/processed "
                "--output reports/v1.1.0"
            ),
            "source": {
                "baseline_revision": BASELINE_REVISION,
                "baseline_engine_sha256": BASELINE_SOURCE_SHA256,
                "current_engine_sha256": file_sha256(ROOT / "app/graph_engine.py"),
                "verifier_sha256": file_sha256(Path(__file__)),
                "method": (
                    "Actual checksum-verified v1.0.0 GraphEngine loaded from local Git and "
                    "current GraphEngine, both reading the same existing data and model artifacts."
                ),
            },
            "dataset": {
                "dataset_sha256": engine.manifest.get("dataset_sha256"),
                "graph_sha256": file_sha256(data_dir / "graph.json"),
                "manifest_sha256": file_sha256(data_dir / "manifest.json"),
                "compounds": len(engine.entities["Compound"]),
                "diseases": len(engine.entities["Disease"]),
            },
            "model": {
                "name": engine.model["name"],
                "model_sha256": engine.model.get("model_sha256"),
                "artifact_sha256": file_sha256(data_dir / "model.json"),
                "evaluation_artifact_sha256": file_sha256(data_dir / "evaluation.json"),
                "refitted": False,
            },
            **result,
            "examples": save_examples(engine, output),
        }
    except (OSError, RuntimeError, ValueError) as error:
        write_json(
            report_path,
            {"status": "failed", "started_at_utc": started, "error": str(error)},
            pretty=True,
        )
        raise
    report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(report_path, report, pretty=True)
    return report


def main() -> int:
    """Write the verification report and exit nonzero if any score changed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--output", type=Path, default=Path("reports/v1.1.0"))
    arguments = parser.parse_args()
    report = verify(arguments.data_dir, arguments.output)
    print(
        json.dumps(
            {key: report[key] for key in ("status", "compared_scores", "max_absolute_difference")}
        )
    )
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
