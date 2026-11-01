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
| http://localhost:8080 | Overview and research workbench |
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
all of its evidence is removed. It requests binding, source-group, selected-PubMed,
conditional-protection and joint group/record certificates. Each is verified
through its live endpoint; a correctly rehashed false claim must still be
rejected. The smoke report retains the complete certificates and actual
verification/rejection results, including the joint audit's independent matrix
witness replays.
Invoke `python infra/smoke.py --base-url URL`
through the Nginx address when ports are customized.

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
