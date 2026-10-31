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

Run `make data`, `make snapshot`, `make lint`, `make test` and `make notebook`.
The PR's fresh runner then executes the complete `make docker-run` path, the HTTP
smoke check, real Neo4j/GDS checks and actual LLM HTTP checks. Preserve failures;
do not convert them to successful fallbacks or skip the provider gate.

When an existing connector cannot write to the repository, an authorized GitHub
UI workflow can transport a tested, checksum-verified Git bundle to a feature
branch. Keep that helper scoped to the expected branch, base, bundle checksum and
tested commit, with only repository contents permission. Never change account
permissions or invent a credential. Remove the transport and helper before the
PR is merged. A human-initiated UI PR and merge provide the normal PR and main
push events; workflow-token pushes alone do not trigger push CI. Any required
workflow approval must be handled explicitly.

## Evidence from the new run

| Artifact | Required content |
| --- | --- |
| `ci-quality.json`, `ci-integration.json` | Checkout SHA, Actions run and attempt, job and start time; each job has a separate context |
| `ollama-model.json` | Actual full model digest, expected digest, size and whether it was reused; the reference default must be `verified` |
| `http_smoke.json` | Live HTTP checks, frontend headers, exact assessment reconstruction and retained unsupported pair |
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
six cases and sixteen exclusion configurations, including compound focus and
unsupported states. Do not package credentials, Git metadata or dependencies.

Tag the tested commit, attach the new evidence, and publish checksums covering
all release assets. Keep earlier releases intact. A previous video or snapshot
may remain useful when clearly versioned; do not relabel it as a recording of
features it does not show. Link the release and the live-source instructions in
the README. Complete classroom submission and personal-defense requirements
according to the instructor's actual instructions.
