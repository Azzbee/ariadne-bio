# Self-hosted API reference assets

`/docs` and `/redoc` use these local distributions, the local ARIADNE mark and a
local copy of the upstream Redocly footer logo.
They require no CDN, remote favicon, Google Fonts or npm install at runtime.
The OpenAPI document is still served by the application at `/openapi.json`.

| Distribution | Pinned version | License | Retained notices |
| --- | --- | --- | --- |
| swagger-ui-dist | 5.34.1 | Apache-2.0 | `swagger-ui-LICENSE`, `swagger-ui-NOTICE`, `swagger-ui-bundle.js.LICENSE.txt` |
| redoc | 2.5.4 | MIT | `redoc-LICENSE`, `redoc.standalone.js.LICENSE.txt`, embedded-worker dependency notices |
| ARIADNE mark | Repository asset | MIT | Project `LICENSE`; copied from `frontend/assets/mark.svg` |

On 2 November 2026, the official npm registry's version-specific metadata and
tarballs were retrieved over HTTPS. Each complete tarball was checked against
its published SHA-512 `dist.integrity` and SHA-1 `dist.shasum` **before** extracting
the listed static files. Package lifecycle scripts were not executed. All
package files retain their original bytes except the explicitly recorded ReDoc
branding-URL localization below. No runtime npm dependency is added.

The ReDoc bundle contains exactly one upstream footer-image URL,
`https://cdn.redoc.ly/redoc/logo-mini.svg`. That exact occurrence is replaced by
`/docs/assets/redocly-logo.svg`. The original SVG is downloaded from the official
URL and served unchanged, preserving the visible Redocly branding. The manifest
records its source URL and checksum, the bundle's original hash/size, the single
replacement and the modified bundle's hash/size. The test reverses the replacement
and verifies that it reconstructs the original bundle hash. The localized bundle
is therefore not described as an unmodified npm archive member.

ReDoc 2.5.4 was the highest stable 2.x release in the official registry when
retrieved. This major version matches the classic-script loader emitted by
FastAPI's `get_redoc_html`. ReDoc 3's ESM distribution requires a different loader
and is not interchangeable with that helper. The retained worker notice belongs
to the worker embedded as a Blob in the 2.x bundle; no separate worker download
is needed. Browser rendering is checked as well as the package's integrity.

`vendor-manifest.json` records the exact metadata/tarball URLs, package integrity,
tarball SHA-256, archive member names, transformations and per-file SHA-256/byte counts. The test
suite checks the served bytes against that inventory and confirms that both
HTML pages reference only local resources. To update, retrieve explicit new
versions, verify each tarball's published integrity, retain the applicable
licenses/notices, replace the selected files, regenerate the inventory and rerun
the route/checksum tests plus actual browser rendering.

The application follows FastAPI's official
[custom documentation assets pattern](https://fastapi.tiangolo.com/how-to/custom-docs-ui-assets/).
It disables default CDN-backed pages, serves a static directory, and supplies
local URLs to `get_swagger_ui_html` and `get_redoc_html`. Swagger's remote
validator is disabled and ReDoc uses `with_google_fonts=False`.
