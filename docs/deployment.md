# Deployment and operational guide

## Full local stack

Install Docker with the Compose v2 plugin, Git and Make, then run:

```bash
git clone https://github.com/Azzbee/ariadne-bio.git
cd ariadne-bio
make docker-run
```

The startup sequence creates `.env` if absent, builds the checksum-verified GDS
image, starts Neo4j and Ollama, downloads the configured model, and starts the API
and frontend. The API prepares graph/model artifacts if needed and performs an
idempotent Neo4j import before serving traffic. Persistent Docker volumes retain
the graph and model between starts.

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

Set these values in `.env` and recreate the API:

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

```bash
make install
make data
make run
```

This starts the deterministic in-memory graph implementation on port 8000.
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

`make test` runs unit and API checks plus the frontend module tests. The coverage
gate is 60% with branch measurement enabled. `make lint` enforces a Pylint score
of at least 9.5 and checks Black formatting. `make notebook` executes every
notebook cell with the current virtual environment's Python kernel.

`make smoke` exercises the running reverse proxy and API. For Neo4j integration,
export the `.env` values as above and run `make test-integration`. The CI workflow
does this against a newly built Compose deployment and retains logs and reports.

## Images and CI

The GitHub workflow pins third-party actions to verified commit SHAs. It
installs pinned Python dependencies, downloads checksummed data, runs tests,
executes the notebook, builds the full stack and exercises the API. Image
publication waits for both quality and integration jobs.

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

## Troubleshooting

| Symptom | Diagnosis and resolution |
| --- | --- |
| First startup takes time | Inspect `make docker-logs`. The first run downloads data and model weights and imports Neo4j. Subsequent starts reuse volumes. |
| Neo4j authentication fails after changing `.env` | The existing data volume retains its configured password. Restore the original password or change it through an authenticated Neo4j session. |
| Model unavailable | Verify the configured base URL and model, or rerun `docker compose --profile llm run --rm ollama-init`. Check the reported agent mode. |
| Port already in use | Change the appropriate `*_PORT` variable in `.env` and recreate services. |
| Download checksum mismatch | Remove only the corrupted raw archive and retry. Do not change the expected checksum to make an unknown file pass. |
| Browser graph empty | Inspect the API error and selected disease. A compound can have no surviving paths after evidence exclusion. This is a valid result. |
| Low available memory | Start with `make docker-core`, close unused services, or use an external LLM provider. Preserve the same graph and scientific protocol. |

`make docker-stop` retains data. `make clean` removes only caches and test
outputs. Destructive volume deletion is not part of routine startup or cleanup.
