"""Create private local configuration without overwriting existing credentials."""

from pathlib import Path
import os
import secrets


def create_environment(directory: Path) -> bool:
    """Create a private .env once, returning whether a file was created."""
    target = directory / ".env"
    template = (directory / ".env.example").read_text(encoding="utf-8")
    content = template.replace(
        "NEO4J_PASSWORD=\n", f"NEO4J_PASSWORD={secrets.token_urlsafe(32)}\n", 1
    )
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(content)
    return True


if __name__ == "__main__":
    created = create_environment(Path(__file__).resolve().parents[1])
    print("Created private .env configuration." if created else "Kept existing .env unchanged.")
