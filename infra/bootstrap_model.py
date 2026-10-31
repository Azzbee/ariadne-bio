"""Prepare one local Ollama model and record its actual, checked identity.

The default manifest is pinned independently of the mutable model tag. Existing
models are never replaced: a mismatch stops startup. Custom models without an
explicit digest are allowed and are reported as unpinned.

Protocol: https://docs.ollama.com/api/tags and
https://github.com/ollama/ollama/blob/main/docs/api.md#pull-a-model
"""

import argparse
from datetime import datetime, timezone
import json
import os
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

DEFAULT_MODEL = "qwen2.5:1.5b"
# SHA-256 of https://registry.ollama.ai/v2/library/qwen2.5/manifests/1.5b.
# Independently verified against the registry and installed Ollama model.
DEFAULT_MODEL_DIGEST = "65ec06548149b04c096a120e4a6da9d4017ea809c91734ea5631e89f96ddc57b"


class ModelIdentityError(RuntimeError):
    """Startup cannot establish the requested model identity."""

    def __init__(self, message: str, report: dict | None = None):
        super().__init__(message)
        self.report = report or {}


def normalize_digest(value: str) -> str:
    """Require a complete SHA-256 identity, allowing the conventional prefix."""
    result = value.removeprefix("sha256:").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", result):
        raise ModelIdentityError("Model digest must contain exactly 64 hexadecimal characters")
    return result


def normalized_name(value: str) -> str:
    """Ollama treats an omitted model tag as latest."""
    return value if ":" in value.rsplit("/", 1)[-1] else value + ":latest"


# This client deliberately exposes one bounded HTTP operation.
class OllamaAPI:  # pylint: disable=too-few-public-methods
    """Small standard-library client retaining normal environment proxy routing."""

    def __init__(self, base_url: str, timeout: float = 1800):
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ModelIdentityError("OLLAMA_HOST must be an HTTP(S) URL")
        if any((parsed.username, parsed.password, parsed.query, parsed.fragment)):
            raise ModelIdentityError(
                "OLLAMA_HOST must not contain credentials, a query or a fragment"
            )
        if not 1 <= timeout <= 1800:
            raise ModelIdentityError(
                "Model initialization timeout must be between 1 and 1800 seconds"
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, path: str, payload: dict | None = None) -> dict:
        """Read bounded JSON; a model pull completes before its identity is checked."""
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            self.base_url + path,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=self.timeout if payload else 30) as response:
                body = response.read(1_048_577)
        except HTTPError as error:
            raise ModelIdentityError(f"Ollama {path} returned HTTP {error.code}") from error
        except (URLError, TimeoutError, OSError) as error:
            raise ModelIdentityError(f"Ollama {path} could not be reached or timed out") from error
        if len(body) > 1_048_576:
            raise ModelIdentityError("Ollama returned an unexpectedly large metadata response")
        try:
            result = json.loads(body)
        except (ValueError, UnicodeError) as error:
            raise ModelIdentityError("Ollama returned invalid JSON metadata") from error
        if not isinstance(result, dict):
            raise ModelIdentityError("Ollama metadata must be a JSON object")
        if result.get("error"):
            raise ModelIdentityError(f"Ollama {path} failed: {result['error']}")
        return result


def find_model(api: OllamaAPI, model: str) -> dict | None:
    """Find the requested local model without matching unrelated tags."""
    models = api.request("/api/tags").get("models")
    if not isinstance(models, list):
        raise ModelIdentityError("Ollama model inventory is missing")
    for item in models:
        if not isinstance(item, dict):
            raise ModelIdentityError("Ollama model inventory contains an invalid record")
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and normalized_name(name) == normalized_name(model):
            return item
    return None


def prepare_model(api: OllamaAPI, model: str, expected_digest: str = "") -> dict:
    """Reuse a verified local model or pull an absent one; never replace a mismatch."""
    if not model or not model.strip():
        raise ModelIdentityError("A model name is required")
    expected = expected_digest or (DEFAULT_MODEL_DIGEST if model == DEFAULT_MODEL else "")
    expected = normalize_digest(expected) if expected else None
    installed = find_model(api, model)
    reused = installed is not None
    if installed is None:
        print(
            f"Downloading absent Ollama model {model}; first startup may take several minutes.",
            file=sys.stderr,
        )
        result = api.request("/api/pull", {"model": model, "stream": False})
        if result.get("status") != "success":
            raise ModelIdentityError("Ollama did not confirm a successful model download")
        installed = find_model(api, model)
    if installed is None:
        raise ModelIdentityError("Ollama completed the pull but the requested model is absent")
    actual = normalize_digest(str(installed.get("digest", "")))
    report = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": installed.get("name") or installed.get("model"),
        "requested_model": model,
        "digest": actual,
        "expected_digest": expected,
        "size_bytes": installed.get("size"),
        "reused_existing_model": reused,
        "status": "verified" if expected else "recorded_unpinned",
        "reproducibility": (
            "Full installed manifest digest matches the expected identity."
            if expected
            else (
                "Custom model identity recorded without an expected digest; "
                "it is not a pinned reproduction."
            )
        ),
    }
    if expected and actual != expected:
        report["status"] = "failed"
        raise ModelIdentityError(
            f"Model identity mismatch for {model}: expected {expected}, observed {actual}. "
            "Startup stopped; no existing model was overwritten. "
            "Review the configured model and digest.",
            report,
        )
    return report


def main() -> int:
    """Write fresh JSON evidence to stdout and a useful error to stderr on failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("OLLAMA_HOST", "http://ollama:11434"))
    parser.add_argument("--model", default=os.getenv("ARIADNE_LLM_MODEL", DEFAULT_MODEL))
    parser.add_argument("--expected-digest", default=os.getenv("ARIADNE_LLM_MODEL_DIGEST", ""))
    arguments = parser.parse_args()
    try:
        report = prepare_model(
            OllamaAPI(arguments.base_url), arguments.model, arguments.expected_digest
        )
    except ModelIdentityError as error:
        report = {**error.report, "status": "failed", "error": str(error)}
        print(json.dumps(report, indent=2))
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
