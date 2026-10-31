# Deployment and operational guide

## Full local stack

Install Docker with the Compose v2 plugin, Git, Make and Python 3 (used once to
generate private local credentials), then run:

```bash
git clone https://github.com/Azzbee/ariadne-bio.git
cd ariadne-bio
make docker-run
```

The startup sequence creates `.env` if absent, builds the checksum-verified GDS
image, starts Neo4j and Ollama, verifies or downloads the configured model, and starts
the API and frontend. The API prepares graph/model artifacts if needed and performs an
idempotent Neo4j import before serving traffic. Persistent Docker volumes retain
the graph and model between starts. A matching installed model is reused without a
pull. Reserve approximately 8 GB available RAM and 20 GB free disk for the local
stack; image extraction requires substantially more space than compressed downloads.

The default Qwen model's full manifest identity is pinned in
[bootstrap_model.py](../infra/bootstrap_model.py). Initialization uses Ollama's
[model inventory](https://docs.ollama.com/api/tags) and
[pull API](https://github.com/ollama/ollama/blob/main/docs/api.md#pull-a-model).
An existing mismatched model stops startup without being overwritten or silently
pulled again. An absent model is pulled once and checked before the API starts.
The actual digest, expected digest, size, reuse status and check time are written
to `reports/ollama-model.json`.

For a different **local** model, set `ARIADNE_LLM_MODEL`. An optional
`ARIADNE_LLM_MODEL_DIGEST` pins its full SHA-256 manifest digest. Without that
explicit pin, the actual identity is recorded as `recorded_unpinned`; it is not
claimed to reproduce the reference model. External providers use the core stack
and do not pass through the local Ollama initializer.

| Address | Service |
| --- | --- |
| http://localhost:8080 | Research workbench |
| http://localhost:8080/docs | Interactive Swagger documentation |
| http://localhost:8000/api/health | Direct API health and execution mode |
| http://localhost:7474 | Neo4j Browser |
| bolt://localhost:7687 | Neo4j Bolt connection |

Host ports are bound to loopback. The Neo4j password is generated locally in a
mode-0600 `.env` file. `make init` never overwrites an existing file. The default
Neo4j username is `neo4j`.

### Core stack without local model download

```bash
make docker-core
```

This starts Neo4j, the API and frontend. The graph tools, ranking and challenge
workflow remain available. Responses report deterministic execution when no
language model is available. For the coursework agent demonstration, run and
verify a live provider with the full stack or configured external service.

### Configured language-model provider

Use `make docker-core`, then set these values in `.env` and recreate the API:

```dotenv
ARIADNE_AGENT_MODE=llm
ARIADNE_LLM_BASE_URL=https://your-compatible-provider.example/v1
ARIADNE_LLM_MODEL=your-selected-model
ARIADNE_LLM_API_KEY=
ARIADNE_LLM_TIMEOUT=120
```

The API key belongs in the ignored local configuration, never in Git or the
frontend. The default Docker model is `qwen2.5:1.5b`, served through Ollama's
OpenAI-compatible endpoint. Model availability and behavior are checked by the
application, and the response mode is visible to the user.

```bash
docker compose up -d --force-recreate api
```

## Native Python development

Install Python 3.11+ (3.12 is the reference), Node.js 18+ (22 in CI), Make and Git.
Python dependencies are hash locked. The frontend has no package dependencies,
but its test runner requires Node. The native API serves the frontend on the
same port; use http://localhost:8000.

```bash
make install
make data
ARIADNE_AGENT_MODE=deterministic make run
```

This explicitly starts the deterministic in-memory implementation on port 8000.
The shared `.env` defaults to the internal Docker Ollama hostname; the command
above prevents accidental attempts to use that hostname from the native process.
To use a running Neo4j service instead, export the local configuration:

```bash
set -a
. ./.env
set +a
export ARIADNE_GRAPH_BACKEND=neo4j
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_DATABASE=neo4j
export ARIADNE_LLM_BASE_URL=http://localhost:11434/v1
.venv/bin/python -m scripts.load_neo4j
make run
```

The Ollama Compose service has no published host port by default. The local URL
above applies to a separately running native Ollama service, or a deliberately
published local port. For the standard Compose application use the internal
`http://ollama:11434/v1` URL already configured.

## Verification commands

`make snapshot` first exports the complete seven-case research edition. Then
`make test` runs unit and API checks plus the frontend module tests. The coverage
gate is 60% with branch measurement enabled. `make lint` enforces a Pylint score
of at least 9.5 and checks Black formatting. `make notebook` executes every
notebook cell with the current virtual environment's Python kernel.

`make smoke` exercises the running reverse proxy and API. For Neo4j integration,
export the `.env` values as above and run `make test-integration`. The CI workflow
does this against a newly built Compose deployment and retains logs and reports.
`make test-llm` verifies actual provider inference, evidence exclusions, rejection,
and named-compound focus against http://127.0.0.1:8080; set
`ARIADNE_TEST_BASE_URL` when testing a different local address. It fails if an
expected LLM success falls back to deterministic execution.

The HTTP smoke check verifies the frontend's actual response headers, reconstructs
both assessment scores, and confirms that a compound remains inspectable after
all of its evidence is removed. It also requests a global binding audit, verifies
the certificate through the live endpoint, and submits a false rank claim with a
recomputed valid content hash. The false claim must still be rejected. The smoke
report retains the full original certificate and verification/rejection results.
Invoke `python infra/smoke.py --base-url URL`
through the Nginx address when ports are customized.

### Exact audit and data-rights inventory

```bash
make audit-licenses
make benchmark-audits
make verify-scores
```

The first target inventories the actual prepared data's license text and missing
metadata; successful execution never means legal clearance. The second runs the
binding-audit workload across every disease's canonical baseline top ten at
budgets zero, one and two, with every compound eligible as a competitor. The third
preserves legacy score parity with the checksum-verified historical implementation
and requires a full Git clone containing that commit. A source ZIP has no Git
history; obtain the normal clone before running that historical regression gate.

The API loads the auditor lazily and keeps a bounded disease-envelope cache.
The first request for a disease computes its local deletion states; subsequent
requests can reuse them. Verification recomputes optimality with the same proven
algorithm in a separate bounded cache and independently replays witnesses with
edited graph matrices. It is not a second independent optimality algorithm.
The scientific tests provide exhaustive global enumeration on small graphs.

Audit input is restricted to `top_k=1..100`, `budget=0..2`, and exact disease and
compound IDs. It always uses the complete graph, independently of any selected
family exclusion. A fitted model is required. No additional database, model
download, API key or container is needed. The canonical audit scorer is separate
from the unchanged legacy ranking scorer; see the [numerical contract](binding_audit_proof.md).

## Images and CI

The GitHub workflow pins third-party actions to verified commit SHAs. It
installs pinned Python dependencies, downloads checksummed data, runs tests,
executes the notebook, builds the full stack and exercises the API. Image
publication waits for both quality and integration jobs. Immediately after checkout, each CI job runs
`infra/prepare_ci_evidence.py --job quality|integration` and records its checkout
SHA and Actions identifiers separately. Quality removes only the outputs it will
rebuild, including generated model/evaluation metadata; integration removes only
operational reports and preserves the prepared scientific artifacts. Quality
also removes the prior v1.2 benchmark and licensing inventory before regenerating
them. This
prevents an early failure from uploading a committed success from an older run.
The source graph, notebook and historical reference reports are preserved.

Images are tagged with both `latest` and the source commit SHA:

```text
ghcr.io/azzbee/ariadne-bio-api:<commit-sha>
ghcr.io/azzbee/ariadne-bio-frontend:<commit-sha>
```

Use the commit tag for a reproducible deployment. A package must be made public
in GitHub package settings and verified with an unauthenticated pull before
claiming that the public-registry rubric item is complete.

## Browser-only research edition

`make snapshot` exports the checked graph/model results for a static hosted
interface. This edition identifies its dataset and model snapshot and can
present candidate rankings, evidence and precomputed exclusion scenarios.
It has no embedded provider credential. A frozen research edition is useful for
review and sharing, while the full Compose stack is the live database and
agent implementation used for the technical demonstration.

Binding audits in this edition are frozen records for the exported compounds,
`top_k` values 1, 5 and 10, and budgets zero, one and two. Their export-time
verification status is recorded. A browser checksum check does not recompute
optimality or edit a live graph. Use the live API to independently reverify an
exported certificate against its matching model and graph identities.

Before using a case file, the client verifies its raw byte count and SHA-256
against the manifest, then checks each audit's dataset/model/graph identities.
A local SHA-256 implementation covers environments without WebCrypto. This binds
data to the served manifest; it does not authenticate an independent publisher
or replace live/offline certificate verification.

## Troubleshooting

| Symptom | Diagnosis and resolution |
| --- | --- |
| First startup takes time | Inspect `make docker-logs`. The first run downloads data and model weights and imports Neo4j. Subsequent starts reuse volumes. |
| Neo4j authentication fails after changing `.env` | The existing data volume retains its configured password. Restore the original password or change it through an authenticated Neo4j session. |
| Model unavailable | Verify the configured base URL and model. For local Ollama, rerun `make docker-run`; it checks existing identity and downloads only an absent model. Check the response mode and model report. |
| Model identity mismatch | Inspect `reports/ollama-model.json`. Startup intentionally stops. Review the configured model and full digest; do not change the expected identity just to make an unknown model pass. No existing model is replaced automatically. |
| Port already in use | Change the appropriate `*_PORT` variable in `.env` and recreate services. |
| Download checksum mismatch | Remove only the corrupted raw archive and retry. Do not change the expected checksum to make an unknown file pass. |
| Browser graph empty | Inspect the API error and selected disease. A compound can have no surviving paths after evidence exclusion. This is a valid result. |
| Low available memory | Start with `make docker-core`, close unused services, or use an external LLM provider. Preserve the same graph and scientific protocol. |

`make docker-stop` retains data. `make clean` removes only caches and test
outputs. Destructive volume deletion is not part of routine startup or cleanup.
