# Release verification

Release evidence must describe the exact tested source revision. A public image,
a local successful test or a previous release report does not establish that a
new revision passed. Both CI jobs therefore start with their own fresh checkout identity and remove
only their prior generated outputs before installing dependencies or running tests.

## Before merging

Use a focused feature branch and an ordinary pull request. Explain the user-visible
problem, implemented behavior, actual validation and any remaining limitation.
Review comments and human contribution claims must describe work that happened;
automated agents do not stand in for a second human teammate.

Run `make data`, `make audit-licenses`, `make benchmark-audits`, `make snapshot`,
`make verify-scores`, `make lint`, `make test` and `make notebook`.
The PR's fresh runner then executes the complete `make docker-run` path, the HTTP
smoke check, real Neo4j/GDS checks and actual LLM HTTP checks. Preserve failures;
do not convert them to successful fallbacks or skip the provider gate.

When an existing connector cannot write, use an already authorized ordinary
GitHub UI upload or edit on the feature branch, then verify that its complete
source tree matches the tested local tree. Normal UI commits, a PR and an
authorized merge generate the usual CI events. Do not introduce a temporary
contents-write import workflow, invent a token or change account permissions to
work around a rejected publication path. If an approval block remains, state
the blocked action and use a permitted alternative or obtain explicit approval.

## Evidence from the new run

| Artifact | Required content |
| --- | --- |
| `ci-quality.json`, `ci-integration.json` | Checkout SHA, Actions run and attempt, job and start time; each job has a separate context |
| `ollama-model.json` | Actual full model digest, expected digest, size and whether it was reused; the reference default must be `verified` |
| `http_smoke.json` | Live HTTP checks, frontend headers, exact assessment reconstruction, retained unsupported pair, full binding certificate, recomputed bound/witness verification and rejection of a rehashed false rank claim |
| `v1.2.0/binding-audit-benchmark.json` | Full disease/top-ten workload, graph/model/scorer identities, exact budget results, local/global state counts, focus-only comparisons and actual runtime |
| `v1.2.0/license-inventory.json` | Actual observed license/source counts and missing metadata, bound to graph bytes; legal clearance remains unassessed |
| `neo4j-junit.xml` | Genuine database and graph-algorithm tests |
| `llm-junit.xml` and `llm-*.json` | Actual planner success, evidence challenge, rejection, and named-compound assessment with correct ranking context |
| Container logs/status and runner resource reports | Startup, service health and disk/memory observations |
| Quality artifacts | Current unit/API/frontend results, coverage, notebook and scientific output identities |

The uploaded evidence is an output of the run. Files preserved in the repository
as historical reference must never substitute for a missing new result. Confirm
the workflow and job conclusions, not just artifact existence.

## Publish and independently verify

After an authorized merge, main CI reruns the gates and publishes API and frontend
images with both `latest` and the full source-commit tag. Verify both packages
anonymously using the OCI registry API or a logged-out container client. Inspect
both tags, compare their manifest digests, check source/revision labels, and verify
all downloaded configuration and layer bytes against their SHA-256 descriptors.
This verifies anonymous image retrieval; container execution is established by
the separate fresh Compose job.

Build a standalone research ZIP from an explicit runtime-file whitelist and the
newly generated snapshot. Include the MIT license, source-data licensing notes,
a local-server README, source revision, and checksums. Extract it and exercise all
seven cases and sixteen exclusion configurations, including compound focus and
unsupported states. Do not package credentials, Git metadata or dependencies.
The v1.2 runtime whitelist must include `audit.js`, `audit-model.js`,
`audit.css` and `integrity.js` along with the prior frontend assets. Exercise recorded audits for
all exported top-k/budget variants and confirm that static verification is
identified as a recorded export-time result, not a live graph recomputation.
The client checks case-file byte counts and SHA-256 values against the served
manifest before parsing/caching. It also binds audit graph/model/dataset identities
to the manifest. These checks detect mixed or corrupted assets; they are not a
signature by an independent authority and do not prove optimality in the browser.

Tag the tested commit, attach the new evidence, and publish checksums covering
all release assets. Keep earlier releases intact. A previous video or snapshot
may remain useful when clearly versioned; do not relabel it as a recording of
features it does not show. Link the release and the live-source instructions in
the README. Complete classroom submission and personal-defense requirements
according to the instructor's actual instructions.
