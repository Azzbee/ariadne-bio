# ARIADNE

**Trace the evidence. Challenge the hypothesis.**

[![CI](https://github.com/Azzbee/ariadne-bio/actions/workflows/ci.yml/badge.svg)](https://github.com/Azzbee/ariadne-bio/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/code-MIT-153f39.svg)](LICENSE)

ARIADNE is a biomedical evidence workbench. Choose a disease, inspect ranked
compound hypotheses, follow exact biological paths, then remove an evidence
family and see how the same model's ranking changes. An agent resolves questions,
calls bounded graph tools, and explains the returned records with an auditable
trace.

**Version 1.2 adds an exact ranking audit:** can this compound leave the top ten
if any one or two recorded binding edges are withdrawn anywhere in the graph,
including competitors' edges? The result gives the worst supported rank, loss-of-support
possibility and replayable witnesses, with a separately callable verifier. The
guarantee is about the fixed model and the declared edge-deletion budget; it does
not certify a treatment, a biological intervention or source-level independence.
See the [method and proof](docs/binding_audit_proof.md) and
[measured audit results](docs/audit_benchmark.md), with
[closest prior art](docs/research_contribution.md).

The prepared Hetionet subset contains **24,456 nodes, 255,730 evidence edges,
137 diseases and 1,552 compounds**. A separate set of 755 recorded treatment
links supports retrospective evaluation. See the checksummed
[manifest](data/processed/manifest.json) and [data sources](docs/data_sources.md).

Research hypotheses are not treatment recommendations. Removing an evidence
family measures sensitivity to the available graph, not a biological intervention.

![ARIADNE evidence workbench with actual Hetionet records](docs/screenshots/workbench.jpg)

## Inspect the published research edition

[Download the standalone research edition](https://github.com/Azzbee/ariadne-bio/releases/latest)
from the release assets. Extract `ariadne-research-edition.zip`, run
`python3 -m http.server 8080 --bind 127.0.0.1` inside it, and open
http://localhost:8080. It needs no Docker, API key or model download. Its recorded
results and deterministic guide are explicitly identified. The release also
includes the narrated demonstration, captions, checksums and verification evidence.

## Run the complete application

Requires Docker with Compose v2, Git, Make and Python 3 (for initial credential
generation). A practical local budget is 8 GB available RAM and 20 GB free disk;
the verified reference CI runner has 16 GB RAM. The pinned Ollama image alone has
about 3.4 GB of compressed layers, before extraction, and the default model is
about 1 GB. Initial startup prepares the checksummed dataset and verifies the
local model's full manifest digest before starting the application.

```bash
git clone https://github.com/Azzbee/ariadne-bio.git
cd ariadne-bio
make docker-run
```

Open **http://localhost:8080**. Interactive API documentation is at
**http://localhost:8080/docs**, and Neo4j Browser is at **http://localhost:7474**.
`make init` generates a private `.env` with a random database password, preserving
existing configuration. The Neo4j username is `neo4j`.

`make docker-run` starts Neo4j 5.26.0 with GDS 2.13.4, FastAPI, Nginx, and a local
Ollama model. `make docker-core` starts the three core services with explicitly
reported deterministic agent behavior unless an external provider is configured.
For a provider, edit the `ARIADNE_LLM_*` settings in `.env`.

The browser-only research edition uses exported, frozen data and reports its
snapshot status. The complete Compose application executes live Neo4j queries
and can call a live language model. [Deployment details](docs/deployment.md).

## The demonstration

1. Select a disease and inspect a compound's direct, interaction and pathway evidence.
2. Open a node or relationship to inspect its identity and available provenance.
3. Exclude gene interactions or pathway membership. Compare ranks, scores and lost paths.
4. Ask the agent to explain the investigation. Inspect its tool trace and citations.
5. Run the binding audit, inspect a worst-case witness and verify its certificate.
6. Open Evaluation to compare the model with baselines and inspect an actual failure.

Version 1.1 keeps the selected compound visible when evidence changes, even when
it falls outside the displayed ranking or loses every supporting path. Its
assessment shows the all-evidence baseline beside the selected scenario, with
exact signed feature contributions that reconstruct both scores. Ask about a
named compound and the agent focuses its evidence and assessment on that compound
while retaining the correctly ordered ranking as context.

The model and scaler stay fixed during challenge mode. Contributions add in
**logit space**, relative to the saved training-feature means; they are not causal
attributions or clinical probabilities. A pair with no surviving paths has no
supported rank; its finite model output is labeled diagnostic. Every evidence
count uses the full permitted graph; displayed paths are bounded and truncation
is reported. See the [model card](docs/model_card.md) and [API contract](docs/api.md).

The binding audit always starts from the complete graph, independently of the
family-exclusion controls. Its canonical float64 scorer uses the same fitted
parameters with an explicit operation order; existing ranking scores remain
unchanged, and the audit reports its baseline difference from the legacy scorer.
It considers all 1,552 compounds as competitors. At budget two, 117,147 local
states cover 66,949,807 possible global deletion subsets by a separability proof;
these are state counts, not a measured runtime speedup. A witness proves that a
rank can occur. Verification also recomputes the bound, because one witness alone
cannot establish optimality.

The complete audit benchmark covers all 137 diseases and 1,330 baseline top-ten
queries. At budget two, 104 remain certified robust and 1,226 are fragile. A
strong margin-aware greedy comparator finds every one of those failures but
underestimates 19 worst supported ranks. The result supports exact certification;
it does not show extra top-ten failure discovery over that stronger heuristic.
The [complete protocol and results](docs/audit_benchmark.md) retain both greedy
comparators, scope differences, numerical identities and actual replay checks.

![Executed retrospective benchmark and its explicit evaluation protocol](docs/screenshots/benchmark.jpg)

## Retrospective retrieval benchmark

Fixed seed 42, 528 training, 113 validation and **114 held-out treatment links**.
Each test query ranks the complete compound universe after masking training and
validation positives for that disease. The language model takes no part in the
ranking or evaluation.

| Scoring method | Recall@10 | MRR | Recovered / 114 |
| --- | ---: | ---: | ---: |
| Typed-path logistic model | 0.0965 | 0.0439 | 11 |
| Direct-overlap baseline | 0.0526 | 0.0365 | 6 |
| Target-degree baseline | 0.0088 | 0.0072 | 1 |
| Total-path-count baseline | 0.0088 | 0.0069 | 1 |

These are modest retrospective retrieval results, not clinical efficacy estimates
or evidence of new drug discovery. The benchmark is transductive and uses
unobserved pairs as sampled training negatives, with their meaning explicitly
limited to absence from this dataset. Full protocol, split identities, coefficients,
ablation results and failure examples are in
[evaluation.json](data/processed/evaluation.json), [model.json](data/processed/model.json)
and the [model card](docs/model_card.md).

## Reproduce and verify

Native development requires Python 3.11+ (3.12 is the tested reference), Node.js
18+ (CI uses 22), Make and Git. Node runs the dependency-free frontend tests;
`make install` installs the Python environment. Generate the snapshot before
running tests to include all seven recorded cases and all sixteen exclusion sets.

```bash
make install          # Python 3.11+; the verified reference runtime is Python 3.12
make data             # Download, checksum, prepare, train and evaluate
make snapshot         # Export every recorded scenario for frontend verification
make audit-licenses   # Inventory actual source-license text and missing metadata
make benchmark-audits # All diseases, top ten, global binding budgets zero to two
make test             # Unit/API tests, branch coverage gate and frontend tests
make lint             # Pylint >=9.5 and Black formatting
make notebook         # Execute every notebook cell with the active interpreter
make verify-scores    # Full legacy score parity; requires the v1.0 Git history
make smoke            # Live HTTP workflow, certificate replay and tamper rejection
make test-integration # Genuine Neo4j/Cypher/GDS tests; see deployment instructions
make test-llm         # Actual provider investigation, challenge routing and rejection
```

Version 1.1 historical verification and interface changes are recorded in the
[1.1 verification notes](docs/releases/v1.1.0.md). The v1.2
[audit methodology](docs/research_contribution.md) describes its additional gates
and bounded claims. The workflow badge
links to actual CI status; configured checks alone are not a successful run.

The published **1.0 historical reference** passed **103 Python tests, 29 frontend tests, 8 genuine
Neo4j/GDS integration tests and 3 actual local-LLM HTTP tests**. A separate clean
Python environment installed the hash-locked dependencies without system packages,
passed the tests at **83.58% branch-aware coverage**, and executed every notebook
cell. The 1.0 source passed **Pylint 10.00/10** and Black. Its immutable evidence:
[fresh-environment evidence](https://github.com/Azzbee/ariadne-bio/blob/v1.0.0/reports/fresh-environment.json),
[database test results](https://github.com/Azzbee/ariadne-bio/blob/v1.0.0/reports/neo4j-junit.xml) and
[actual LLM test results](https://github.com/Azzbee/ariadne-bio/blob/v1.0.0/reports/llm-junit.xml).

Measured query plans reduced database hits from **48,913 to 2** for an equivalent
identity lookup. Warm local timings and complete PROFILE plans are retained in
[query optimization evidence](reports/query_optimization.json). These timings
describe the measured machine, not a production performance guarantee.

The current CI workflow is configured to verify selected-compound assessment,
exact score reconstruction, retained unsupported pairs, frontend response headers,
the full-dataset binding audit, rejected rehashed certificate claims, and a live
LLM request that overrides stale compound selection. It deletes old
operational reports before collecting fresh evidence for the actual checkout,
records the default model identity, and publishes API and frontend images only
after quality and full-stack integration pass. Release proof is tied to the
verified source commit; [release instructions](docs/releasing.md) describe it.
The workflow badge above reports its actual status. Registry locations:
[API image](https://github.com/Azzbee/ariadne-bio/pkgs/container/ariadne-bio-api)
and [frontend image](https://github.com/Azzbee/ariadne-bio/pkgs/container/ariadne-bio-frontend).
The published release includes anonymous manifest, configuration and layer-byte
verification. Repeat that verification for each release commit.

## Architecture

```mermaid
flowchart TD
    U["Research interface · Nginx :8080"] --> A["FastAPI · :8000"]
    A --> N["Neo4j + GDS · :7687"]
    A --> M["Frozen graph features + model"]
    A --> L["LangGraph investigation"]
    L --> N
    L --> O["Local or configured LLM"]
    H["Checksummed Hetionet JSON"] --> E["Idempotent import + evaluation"]
    E --> N
    E --> M
```

Neo4j stores typed, namespace-qualified entities and provenance. Sparse feature
matrices support reproducible full-candidate ranking. GDS exposes graph proximity
and compound target similarity as separate analysis tools. The agent explains
structured tool results. The language model never determines benchmark labels or
model scores; those come from the recorded data and deterministic graph pipeline.

For an exported binding certificate, the offline verifier needs no running API,
Neo4j or language model:

```bash
.venv/bin/python -m scripts.verify_audit binding-audit.json \
  --data-dir data/processed --output audit-verification.json
```

It checks the full claims and replays the witnesses against the matching local
graph/model identities. Exit zero means verified; exit one means invalid.

## API examples

```bash
curl 'http://localhost:8080/api/diseases?q=asthma'
curl 'http://localhost:8080/api/rankings/Disease::DOID:2841?limit=5'
curl 'http://localhost:8080/api/evidence/Disease::DOID:2841/Compound::DB00961?limit=8'
curl 'http://localhost:8080/api/assessment/Disease::DOID:10652/Compound::DB00184?exclude=INTERACTS'
curl -X POST 'http://localhost:8080/api/challenge' \
  -H 'Content-Type: application/json' \
  -d '{"disease_id":"Disease::DOID:2841","exclude":["INTERACTS"],"limit":5}'
curl -X POST 'http://localhost:8080/api/agent' \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain Nicotine for Alzheimer disease","disease_id":"Disease::DOID:10652","compound_id":"Compound::DB00184","exclude":["INTERACTS"]}'
```

## Documentation

| Question | Document |
| --- | --- |
| How is the graph modeled? | [Architecture and schema](docs/architecture.md) |
| Why these choices instead of a generic generated graph? | [Anti-genericity appendix](docs/anti_genericity.md) |
| What is the new research claim, and what already exists? | [Contribution and prior art](docs/research_contribution.md) |
| What exactly does the ranking certificate prove? | [Binding-audit proof and numerical contract](docs/binding_audit_proof.md) |
| What did the complete audit and stronger baseline actually find? | [Audit benchmark and limitations](docs/audit_benchmark.md) |
| How are leakage, candidates and failure cases handled? | [Model card](docs/model_card.md) |
| Where did the data come from, and under what terms? | [Data sources and licenses](docs/data_sources.md) |
| Which license restrictions and gaps are actually recorded? | [Observed license inventory](docs/licensing_audit.md) |
| How would commercial value be tested? | [Prospective pilot protocol](docs/commercial_pilot.md) |
| What does each API response mean? | [API contract and examples](docs/api.md) |
| How do I release a tested source revision? | [Release verification](docs/releasing.md) |
| How do I run, configure and troubleshoot it? | [Deployment](docs/deployment.md) |
| What does each grading criterion map to? | [Rubric evidence matrix](docs/rubric.md) |
| What should the recorded demonstration show? | [Nine-minute walkthrough](docs/demo_script.md) |
| What was automated and who contributed? | [Authorship and AI assistance](docs/authorship.md) |

The source code is [MIT licensed](LICENSE). Dataset source licenses remain with
their respective owners. This research dataset is not presented as commercially
cleared; the license inventory records noncommercial declarations and missing
terms, without making automated legal decisions. The original Hetionet paper is
[Himmelstein et al., eLife 2017](https://doi.org/10.7554/eLife.26726).
