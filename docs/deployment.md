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

The base [Compose file](../docker-compose.yml) leaves the provider URL empty.
After model initialization, `make docker-run` also applies
[docker-compose.llm.yml](../docker-compose.llm.yml), which supplies the internal
Ollama endpoint unless an explicit provider URL is configured. If manually
recreating the API of an already initialized full stack, retain that overlay:

```bash
docker compose -f docker-compose.yml -f docker-compose.llm.yml \
  --profile llm up -d --force-recreate api
```

Use `make docker-run` for the complete ordered bootstrap. Commands such as
`docker compose logs`, `exec`, `cp`, `ps` and `down` do not recreate the API and
do not require the overlay.

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
| http://localhost:8080 | Overview and research workbench |
| http://localhost:8080/docs | Interactive Swagger documentation |
| http://localhost:8080/redoc | Alternative API reference |
| http://localhost:8000/api/health | Direct API health, graph backend and agent configuration |
| http://localhost:7474 | Neo4j Browser |
| bolt://localhost:7687 | Neo4j Bolt connection |

Host ports are bound to loopback. The Neo4j password is generated locally in a
mode-0600 `.env` file. `make init` never overwrites an existing file. The default
Neo4j username is `neo4j`.

Swagger UI and ReDoc are served with pinned, self-hosted JavaScript/CSS and the
local ARIADNE favicon. They load the same-origin `/openapi.json` and do not require
CDN availability, Google Fonts or a runtime npm install. The
[asset inventory and licenses](../app/static/docs/README.md) record official npm
tarball integrity verification and checksums. Nginx proxies `/docs/assets` to
FastAPI along with the existing documentation routes.

### Core stack without local model download

```bash
make docker-core
```

This starts Neo4j, the API and frontend. The graph tools, ranking and challenge
workflow remain available. With the default empty `ARIADNE_LLM_BASE_URL` and
`ARIADNE_AGENT_MODE=auto`, planning uses deterministic tools without attempting
a provider connection. An explicitly configured provider URL remains active.
For core-only use after an upgrade, clear an older
`ARIADNE_LLM_BASE_URL=http://ollama:11434/v1` value in `.env`; initialization
preserves existing configuration rather than replacing it.

Health reports configured `auto` or `llm` policy when a provider is configured;
this does not prove that inference succeeded. A completed investigation reports
its actual mode, and rejection/error traces explain attempted workflows. For
the coursework agent demonstration, require a successful request using the
full local-model stack or a configured external provider.

### Configured language-model provider

Use `make docker-core`, then set these values in `.env` and recreate the API:

```dotenv
ARIADNE_AGENT_MODE=llm
ARIADNE_LLM_BASE_URL=https://your-compatible-provider.example/v1
ARIADNE_LLM_MODEL=your-selected-model
ARIADNE_LLM_API_KEY=
ARIADNE_LLM_TIMEOUT=120
```

Set the API key in ignored local configuration if the provider requires one;
never place it in Git or the frontend. The default local Docker model is
`qwen2.5:1.5b`, served through Ollama's OpenAI-compatible endpoint. `llm` mode
rejects a failed provider invocation; `auto` may fall back and discloses that
deterministic execution. The response status and trace accompany its mode.

```bash
docker compose up -d --force-recreate api
```

## Native Python development

Install Python 3.11+ (3.12 is the reference), Node.js, Make and Git. The plain
frontend module tests support Node 18+; the complete browser gate requires
Node 20+ (22 in CI). Python dependencies are hash locked. The browser client has
no runtime package dependencies; the browser test harness uses pinned Playwright.
The native API serves the frontend on the same port; use http://localhost:8000.

```bash
make install
make prepare-data
ARIADNE_AGENT_MODE=deterministic make run
```

This explicitly starts the deterministic in-memory implementation on port 8000.
`make prepare-data` preserves the retained model and evaluation; `make data`
deliberately fits a new model. The [reproduction guide](reproducibility.md)
explains which reports must be refreshed after a refit. A newly created `.env`
has an empty provider URL; the explicit deterministic mode also handles an older
local configuration without attempting its provider.

To use a running Neo4j service instead, keep host port 8000 free for the native
API and export the local configuration. This example still uses deterministic
planning, so it needs no language-model service:

```bash
make init
set -a
. ./.env
set +a
export ARIADNE_GRAPH_BACKEND=neo4j
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_DATABASE=neo4j
export ARIADNE_AGENT_MODE=deterministic
.venv/bin/python -m scripts.load_neo4j
make run
```

For native LLM use, configure a provider reachable from the host. For example,
`http://localhost:11434/v1` applies to a separately running native Ollama service
or a deliberately published local port, with `ARIADNE_AGENT_MODE=llm` and the
matching model name. The Compose Ollama service has no host-published port by
default. Its internal `http://ollama:11434/v1` address is supplied to the
containerized API by the full-stack overlay; it is not a native host endpoint.

## Verification commands

`make test` runs unit and API checks plus the frontend module tests. Run
`make snapshot` first to export the complete seven-case research edition and
include its actual-case frontend tests; snapshot-dependent tests report skips
when no export exists. The coverage gate is 60% with branch measurement enabled.
`make lint` enforces a Pylint score of at least 9.5 and checks Black formatting.
`make notebook` validates artifact identities and executes every notebook cell
with the current virtual environment's Python kernel into `demo.executed.ipynb`.
It does not need a browser snapshot or silently refit the model.

With native dependencies and graph data prepared, the default empty-provider
configuration can verify both core and full-stack behavior:

```bash
make docker-core
python3 infra/smoke.py --core-only --output reports/core-smoke.json
make test INTEGRATION=1
make docker-run
make test-llm
make smoke
```

The core smoke gate requires a completed deterministic investigation with
citations from actual Neo4j evidence. `make test INTEGRATION=1` adds genuine
Neo4j/Cypher/GDS tests to the ordinary unit/API/frontend command; it reads local
database credentials from `.env` or the environment and fails when the requested
database is unconfigured or unavailable. `make test-integration` remains an
equivalent direct entrypoint for only the database suite. CI is configured to
test the core stack before enabling the local model and to retain both results.
Successful execution must still be established for the revision being released.

`make test-llm` verifies actual provider inference, evidence exclusions, rejection,
and named-compound focus against http://127.0.0.1:8080; set
`ARIADNE_TEST_BASE_URL` when testing a different local address. It fails if an
expected LLM success falls back to deterministic execution.

The HTTP smoke check verifies the frontend's actual response headers, reconstructs
both assessment scores, and confirms that a compound remains inspectable after
all of its evidence is removed. It requests binding, source-group, selected-PubMed,
conditional-protection and joint group/record certificates. Each is verified
through its live endpoint; a correctly rehashed false claim must still be
rejected. The smoke report retains the complete certificates and actual
verification/rejection results, including the joint audit's independent matrix
witness replays.
Invoke `python infra/smoke.py --base-url URL`
through the Nginx address when ports are customized.

### Real browser verification

The Chromium gate uses native browser controls and actual exported cases. It
requires Node 20+, the Python environment and prepared graph/model, a complete
snapshot, and the locked Playwright installation:

```bash
make install
make prepare-data
make snapshot
npm --prefix frontend ci --ignore-scripts
cd frontend
npx playwright install --with-deps chromium
cd ..
make test-browser
```

The six scenarios cover checkbox/ranking restoration, native details and form
submission, view navigation/source inspection, a verified joint-certificate
download, Swagger execution of the health endpoint, and ReDoc endpoint
navigation. The certificate's downloaded bytes are compared with the exported
case. Both API-reference scenarios block nonlocal requests, so a hidden CDN,
font or script dependency fails the check.

The harness starts temporary loopback servers at **4173** for the exported
interface and **4180** for an isolated native API. Override them with
`ARIADNE_BROWSER_PORT` and `ARIADNE_BROWSER_API_PORT` if needed. The API uses the
prepared data without refitting, forces memory/deterministic operation, clears
provider credentials and does not load `.env`. Live Neo4j/GDS and real-provider
checks remain separate integration gates. `make test-browser` uses
`.venv/bin/python`; `make test-browser PYTHON=python` selects another prepared
interpreter, as in CI.

Missing generated data fails explicitly. Results are retained under
`reports/browser/`: JUnit, JSON, downloaded certificate bytes, and screenshots
and traces for failures. An installed Chromium/Chrome binary can be selected
with `ARIADNE_BROWSER_EXECUTABLE`; the default uses Playwright's installed
Chromium. CI is configured to run this gate after snapshot export, and its
actual run status must be checked for the submitted revision.

### Certificate transport limits

The three verification routes, `/api/audit/verify`, `/api/provenance/audit/verify`
and `/api/mixed/audit/verify`, accept HTTP request bodies up to **1 MiB** through
Nginx. This accommodates exported JSON with indentation and whitespace. The API
independently bounds the parsed certificate content at **256 KiB**. Ordinary
requests retain Nginx's **32 KiB** body cap.

The full smoke gate replays actual valid certificates on all three routes with
bodies larger than 32 KiB, requires HTTP 422 for oversized certificate content,
and requires HTTP 413 above the 1 MiB transport limit. It also checks the ordinary
request cap. These checks exercise the reverse proxy rather than only a direct
FastAPI test client; their results appear under `certificate_transport` in the
smoke report. See [Nginx configuration](../nginx.conf) and
[smoke implementation](../infra/smoke.py).

### Exact audit and data-rights inventory

```bash
make audit-licenses
make benchmark-audits
make benchmark-provenance
make benchmark-mixed
make provenance-controls
make verify-scores
```

The license target inventories the actual prepared data's license text and
missing metadata; successful execution never means legal clearance. Each audit
benchmark covers every disease's canonical baseline top ten with all compounds
eligible as competitors. The binding and provenance workloads cover budgets zero,
one and two in their respective units. The joint workload covers all four cells
of a source-group budget of zero or one and a surviving-record budget of zero or
one; group and record budgets remain separate. `provenance-controls` reproduces
the disclosed, size-matched random controls for two postselected examples.

`verify-scores` preserves legacy score parity with the checksum-verified
historical implementation and requires a full Git clone containing that commit.
A source ZIP has no Git history; obtain the normal clone before running that
historical regression gate. The [release guide](releasing.md) explains how to
replay the retained CI certificates using their original fitted model, including
the separate joint-research job's artifacts.

The API loads auditors lazily and keeps bounded caches. The first request for a
disease computes the relevant local states or group scenarios; subsequent
requests can reuse them. Verification recomputes optimality with the same proven
algorithm in separate bounded caches and independently replays witnesses with
edited graph matrices. It is not a second independent optimality algorithm.
The scientific tests compare the claimed bounds with exhaustive global
enumeration on small graphs, including overlapping groups and residual records.

Audit input is restricted to `top_k=1..100` and exact disease and compound IDs.
Binding and provenance use `budget=0..2`; the joint API accepts separate
`group_budget=0..1` and `edge_budget=0..1`. Explicit annotation-group selections
contain 1..16 distinct IDs; source groups are the default and PubMed groups
require a selection. All audits start from the complete graph, independently of
any selected family exclusion. A fitted model is required. No additional
database, model download, API key or container is needed. The canonical audit
scorer is separate from the unchanged legacy ranking scorer; see the
[numerical contract](binding_audit_proof.md) and [API contract](api.md).

### Synthetic timing comparison

```bash
make benchmark-mixed-scaling
```

This separate workload compares the joint envelope solver with complete-world
sparse recomputation on 24 generated graphs: 8, 16, 32 or 64 compounds; four or
eight source groups; and three fixed seeds. Each graph uses the same canonical
top-three cohort for both methods, with three matched trials and cold arithmetic
caches. Shared graph loading and cohort selection, solver setup, solving and
certificate verification have separate timing fields. These synthetic results
do not establish a production speedup or performance on a larger real graph.

The target writes `reports/v1.4.0/scaling/`. Keep that complete output directory,
including both JSON reports and all generated
`inputs/` directories. The [protocol](mixed_scaling.md) explains the independent
enumeration and paired timing summaries. For a reference execution that requires
a clean Git checkpoint, add `--require-clean` and choose an absolute output
directory outside the checkout when invoking the CLI directly:

```bash
.venv/bin/python -m scripts.benchmark_mixed_scaling \
  --require-clean --output-dir /tmp/ariadne-mixed-scaling
```

A normal development run records its actual
dirty state and scientific file hashes; running `make data` first can change
tracked model/evaluation files and therefore cannot establish a clean checkout.

## Images and CI

The GitHub workflow pins third-party actions to verified commit SHAs. It
installs pinned Python dependencies, downloads checksummed data, runs tests,
executes the notebook, builds the full stack and exercises the API. Image
publication waits for quality, integration and joint research to succeed for the
same source revision. Immediately after checkout, each CI job runs
`infra/prepare_ci_evidence.py --job quality|integration|mixed` and records its
checkout SHA and Actions identifiers separately. Quality removes only its
generated model/evaluation metadata, benchmark outputs and operational reports;
the joint job separately clears its fit and v1.4 reports; integration removes
its operational reports before creating a fresh Compose deployment. Each job
retains its own model and evidence. This prevents an early failure from
uploading a committed success in a slot that should describe the new run.
The source graph, notebook and reference reports outside each job's declared
outputs are preserved.

After the live HTTP smoke check, CI copies `model.json`, `manifest.json` and
`evaluation.json` directly from the API container into `reports/live-*.json`.
The live-artifact gate checks the model's parameter self-hash and binds every
binding/provider/conditional/PubMed/joint smoke certificate to the copied model and
prepared graph. These files allow offline replay of the actual live certificates.
The quality fit, joint-research fit, committed research-snapshot model and
container fit remain separate origins. Matching seeds or retrieval ranks do not
establish identical fitted parameters. The three artifacts are named
`quality-evidence`, `mixed-evidence` and `integration-evidence`; use the matching
`infra.replay_ci_certificates --kind` value described in the release guide.

Each job also runs that strict retained-model replay as a required gate before
upload. Quality and joint research read their current checkout's evidence;
integration reads `reports/` and reconstructs the engine with the exact
`live-model.json` copied from the API container, never the host's fresh fit.
All three check the actual prepared graph bytes, fitted-parameter self-hash,
certificate scope, recomputed bounds and independent matrix witnesses.
The replay writes outside the input tree under `$RUNNER_TEMP`; only exit zero
allows its receipt to be copied to `reports/ci-<kind>-replay.json` for upload.
Initial per-job cleanup removes old receipts, and a failed replay fails the job.

This in-job gate complements the release check on another runtime. Download all
three actual artifact ZIPs from both the PR run and post-merge main run, verify
their GitHub-provided digests, retain each original archive and independently
replay its retained inputs. The [release guide](releasing.md) gives the exact
commands and separates those six downloads from local reconstructions and
previously saved verdicts.

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
The Overview is static introductory content; it loads a research case only when
the visitor enters the workbench. Existing case and audit deep links still open
their selected investigation directly.
It has no embedded provider credential. A frozen research edition is useful for
review and sharing, while the full Compose stack is the live database and
agent implementation used for the technical demonstration.

Binding audits in this edition are frozen records for the exported compounds,
`top_k` values 1, 5 and 10, and budgets zero, one and two. Their export-time
verification status is recorded. A browser checksum check does not recompute
optimality or edit a live graph. Use the live API to independently reverify an
exported certificate against its matching model and graph identities.

Provenance presets cover top ten with group budgets one and two. Joint presets
cover top ten with one source group and one surviving record, retaining all four
budget cells and their witnesses. Custom PubMed selections, protected-group
assumptions and other unexported scopes require the live API. Missing presets
remain explicitly unavailable; separate record and group certificates cannot
be combined in the browser to manufacture a joint guarantee.

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

## Prepared graph identity and existing volumes

Version 1.3 binds a completed Neo4j import to both the original dataset archive
SHA-256 and the exact prepared `graph.json` SHA-256. The importer inspects the
database before creating constraints or writing records. An existing different
graph, a nonempty unmarked database, an incomplete import or a legacy marker
without a prepared-graph identity is rejected. A completed import of the same
graph remains idempotent. The completion marker is written only after all
record batches, index readiness and node/relationship inventory checks succeed.
API startup checks both identities and the recorded inventory as well.

The previous version's marker identifies only the source archive. Equal archive
identities cannot establish equal prepared graphs, so version 1.3 does not
silently adopt or clear that database. Preserve it and create an explicitly new
Compose project when upgrading a legacy local volume:

```bash
make docker-stop
make docker-run COMPOSE='docker compose -p ariadne-v13'
```

The first command stops the original project without deleting its volumes. The
second uses new project-scoped volumes and reuses the local credential
configuration. Use `COMPOSE='docker compose -p ariadne-v13'` for subsequent
`docker-logs`, `docker-stop` and other Compose targets for that project. Ports
must be free; choose new port settings if both projects should run together.
Do not edit an old database's checksum marker to bypass the check.

This guard protects the normal single-writer initialization workflow against
accidentally mixing prepared datasets. Inventory counts are not an independent
cryptographic attestation of every live database property, and concurrent
external database mutations are outside this deployment contract. The importer
continues to target the prepared Hetionet schema; this is not a general-purpose
customer-data ingestion product.

## Correlated provenance audits

`make benchmark-provenance` evaluates the canonical top-ten workload under
withdrawals of zero, one or two observed BINDS provider groups. Every selected
group removes all binding records bearing that annotation; overlapping records
are removed once. Other relation families and the fitted model remain fixed.
The live API also supports an explicit selection of up to 16 imported PubMed
groups. This is a finite stress scenario over recorded annotations, not a claim
that each provider or PMID is an independent experiment.

The same certificate format carries a minimum-cardinality conditional protection
plan: additional groups that must be assumed unavailable for withdrawal to block
every failing scenario in the declared space. Review completion does not itself
establish that assumption, and an overlapping unprotected group can still remove
the same record. See the [user guide](provenance_audit.md) and
[proof](provenance_audit_proof.md).

The new audit computes edited matrices in memory. It never deletes records from
Neo4j or changes the source graph/model files. Its static research edition stores
explicitly recorded certificates; use the live API or offline verifier for a new
computation against the matching graph and model.
