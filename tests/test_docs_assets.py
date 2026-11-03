"""Keep both API reference UIs usable without a CDN or external font service."""

from hashlib import sha256
from html.parser import HTMLParser
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.config import Settings
from app.main import create_app
from app.service import EvidenceService
from tests.test_graph_engine import create_fixture_engine

ASSETS = Path(__file__).resolve().parents[1] / "app" / "static" / "docs"


class PageResources(HTMLParser):
    """Collect resource URLs a browser must resolve to render the reference."""

    def __init__(self):
        super().__init__()
        self.resources = []
        self.spec_urls = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag in {"script", "img"} and attributes.get("src"):
            self.resources.append(attributes["src"])
        if tag == "link" and attributes.get("href"):
            self.resources.append(attributes["href"])
        if tag == "redoc":
            self.spec_urls.append(attributes.get("spec-url"))


@pytest.fixture
def docs_client(tmp_path):
    """Exercise the real route order, middleware, lifespan and static mount."""
    service = EvidenceService(Settings(), engine=create_fixture_engine(tmp_path))
    with TestClient(create_app(Settings(), service=service)) as client:
        yield client


@pytest.mark.parametrize("route", ["/docs", "/redoc"])
def test_reference_pages_load_only_local_resources_and_real_openapi(docs_client, route):
    response = docs_client.get(route)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    parser = PageResources()
    parser.feed(response.text)
    assert len(parser.resources) >= 2
    assert "/docs/assets/mark.svg" in parser.resources
    for resource in parser.resources:
        assert resource.startswith("/docs/assets/"), resource
        asset = docs_client.get(resource)
        assert asset.status_code == 200
        assert asset.headers["X-Content-Type-Options"] == "nosniff"
        assert not asset.headers["content-type"].startswith("text/html")
    assert "fonts.googleapis.com" not in response.text
    assert "cdn.jsdelivr.net" not in response.text
    assert "/openapi.json" in response.text
    if route == "/redoc":
        assert parser.spec_urls == ["/openapi.json"]
    else:
        assert '"validatorUrl": null' in response.text
        assert "/docs/oauth2-redirect" in response.text

    schema = docs_client.get("/openapi.json").json()
    assert "/api/evidence/{disease_id}/{compound_id}" in schema["paths"]
    assert "/api/agent" in schema["paths"]
    assert not any(path.startswith(("/docs", "/redoc")) for path in schema["paths"])


def test_served_assets_match_verified_package_and_license_inventory(docs_client):
    manifest_response = docs_client.get("/docs/assets/vendor-manifest.json")
    assert manifest_response.status_code == 200
    manifest = manifest_response.json()
    assert manifest == json.loads((ASSETS / "vendor-manifest.json").read_text())
    assert {(package["name"], package["version"]) for package in manifest["packages"]} == {
        ("swagger-ui-dist", "5.34.1"),
        ("redoc", "2.5.4"),
    }
    for package in manifest["packages"]:
        assert package["integrity"].startswith("sha512-")
        assert package["tarball_url"].startswith("https://registry.npmjs.org/")
    declared = {entry["path"] for entry in manifest["files"]}
    assert {"swagger-ui-LICENSE", "swagger-ui-NOTICE", "redoc-LICENSE"} <= declared
    assert "swagger-ui-bundle.js.LICENSE.txt" in declared
    assert "redoc.standalone.js.LICENSE.txt" in declared
    assert "d87bcbdbea8f8f5aa26f.worker.js.LICENSE.txt" in declared
    assert "redocly-logo.svg" in declared
    # FastAPI's helper emits a classic script. The v3 ESM distribution cannot run there.
    bundle = (ASSETS / "redoc.standalone.js").read_bytes()
    assert b"import.meta" not in bundle
    bundle_entry = next(
        entry for entry in manifest["files"] if entry["path"] == "redoc.standalone.js"
    )
    transformation = bundle_entry["transformations"]
    assert len(transformation) == 1
    change = transformation[0]
    assert change["from"] == "https://cdn.redoc.ly/redoc/logo-mini.svg"
    assert change["to"] == "/docs/assets/redocly-logo.svg"
    assert change["matches"] == 1
    assert bundle.count(change["to"].encode()) == 1
    assert change["from"].encode() not in bundle
    original = bundle.replace(change["to"].encode(), change["from"].encode())
    assert len(original) == bundle_entry["upstream_original_bytes"]
    assert sha256(original).hexdigest() == bundle_entry["upstream_original_sha256"]
    for entry in manifest["files"]:
        content = docs_client.get("/docs/assets/" + entry["path"])
        assert content.status_code == 200, entry["path"]
        assert len(content.content) == entry["bytes"]
        assert sha256(content.content).hexdigest() == entry["sha256"]
        assert content.content == (ASSETS / entry["path"]).read_bytes()


def test_documentation_auxiliary_routes_do_not_fall_through_to_frontend(docs_client):
    assert docs_client.get("/docs/oauth2-redirect").status_code == 200
    assert docs_client.get("/docs/assets/missing-bundle.js").status_code == 404
    logo = ASSETS.parents[2] / "frontend" / "assets" / "mark.svg"
    assert (ASSETS / "mark.svg").read_bytes() == logo.read_bytes()
