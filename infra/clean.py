"""Remove only reproducible Python caches and generated test outputs."""

from pathlib import Path
import shutil


def clean(directory: Path) -> None:
    """Preserve code, .env, virtual environments, scientific data and reports."""
    for folder in ("app", "scripts", "tests", "infra"):
        for cache in (directory / folder).rglob("__pycache__"):
            shutil.rmtree(cache)
    for filename in (".pytest_cache", "htmlcov"):
        shutil.rmtree(directory / filename, ignore_errors=True)
    for filename in (".coverage", "coverage.xml", "reports/junit.xml"):
        (directory / filename).unlink(missing_ok=True)


if __name__ == "__main__":
    clean(Path(__file__).resolve().parents[1])
    print("Removed caches and test output. Preserved source, credentials and scientific data.")
