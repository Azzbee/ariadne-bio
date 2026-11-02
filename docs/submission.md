# Coursework submission guide

**ARIADNE investigates which drug–disease hypotheses a biomedical knowledge
graph supports, shows the underlying evidence, and tests whether the ranking
survives changes to that evidence.** The complete application combines Neo4j,
GDS, FastAPI, a bounded LangGraph agent, a research interface and exact audit
certificates. Its results are research hypotheses, not treatment advice.

## Start here

| Question | Direct evidence |
| --- | --- |
| What was built and why is a graph necessary? | [README, graph schema and modeling comparison](../README.md#architecture), [full rationale](anti_genericity.md). |
| Does the complete application run? | [Docker startup below](#run-the-complete-application), [deployment and troubleshooting](deployment.md). |
| What should the demonstration cover? | [9½-minute script](demo_script.md), including interface, code, actual provider inference and rejected invalid provider output. |
| Can I inspect the science without running Docker? | [Executed notebook](../demo.ipynb), [preserved-reference reproduction](reproducibility.md), [model card](model_card.md). |
| Where is each grading requirement demonstrated? | [100-point rubric evidence matrix](rubric.md). |
| What is the research addition? | [Joint-audit explanation](mixed_audit.md), [proof](mixed_audit_proof.md), [complete measured results](mixed_audit_results.md). |
| Who contributed, and what was automated? | [Authorship and AI assistance](authorship.md), [actual PR history](https://github.com/Azzbee/ariadne-bio/pulls), [individual defense guide](defense_guide.md). |

## Verification and version status

This checkout is the **v1.4.1 submission candidate**, checked on **2 November
2026**. It fixes native browser controls and certificate transport, separates
core-only startup from local-model startup, preserves the reference notebook's
scientific identities, and serves both API references without external requests.
The currently sealed public baseline is **v1.4.0**. Its Neo4j/GDS/LLM results
must not be relabeled as a passing full-stack run for this update.

| Item | Available evidence or current status |
| --- | --- |
| Public repository | [Azzbee/ariadne-bio](https://github.com/Azzbee/ariadne-bio). |
| Sealed baseline source | [v1.4.0](https://github.com/Azzbee/ariadne-bio/tree/v1.4.0), commit [`8077a8944def2ef7b432bd9c3539878ec24769da`](https://github.com/Azzbee/ariadne-bio/commit/8077a8944def2ef7b432bd9c3539878ec24769da). |
| Baseline download and verification | [v1.4.0 release assets](https://github.com/Azzbee/ariadne-bio/releases/tag/v1.4.0): source, research edition, executed notebook, verification archive, manifest and SHA-256 checksums. |
| Submission-readiness update | **v1.4.1**. The generated `release-manifest.json` binds the source archive, research edition and executed notebook to one exact Git commit. Local evidence is distributed in the separate verification archive; public publication and a matching full-stack CI run must be checked independently. |
| Current local quality gates | **744 Python tests**, **170 frontend tests** and **6 real Chromium scenarios** passed. Combined line/branch coverage **93.08%**; Pylint **9.90/10**; formatting passed. The seven invalid-provider-output cases are included in the Python total. |
| Current execution evidence | All **14 notebook code cells** executed. Live Nginx/FastAPI smoke passed using the **memory backend and deterministic planner**, including certificate replay and size limits. Swagger executed a live health request; ReDoc navigation worked; both made zero nonlocal requests. |
| CI | [Actual workflow runs](https://github.com/Azzbee/ariadne-bio/actions/workflows/ci.yml). Match the run's commit to the version being assessed; a badge for another revision is insufficient. |
| Public images | [API](https://github.com/Azzbee/ariadne-bio/pkgs/container/ariadne-bio-api), [frontend](https://github.com/Azzbee/ariadne-bio/pkgs/container/ariadne-bio-frontend); release evidence binds anonymous image verification to a source commit. |
| Merged implementation evidence | [Merged PR #1](https://github.com/Azzbee/ariadne-bio/pull/1) and [complete PR history](https://github.com/Azzbee/ariadne-bio/pulls); this alone does not establish one substantial PR per registered member. |
| Current demonstration video | `ariadne-v1.4.1-walkthrough.mp4`: **8 min 23 sec**, captioned, with disclosed synthetic narration. It shows the current interface and code, and explicitly labels the earlier v1.4.0 full-stack provider evidence. SHA-256: `4afdc2275bdf1b182e191bddb0aae61a221e1668d486b4a83b96c592f48ba756`. Video and reproducible production sources are separate hand-in artifacts. |
| Project registration | The registered team's public repository URL was entered in the project information spreadsheet and read back successfully on **2 November 2026**. |
| Moodle hand-in | The signed-in assignment was checked on **2 November 2026**: due **Monday 2 November 2026, 23:59 Europe/Paris**; status **No submissions**, last modified **—**. Submission is held until the team's explicit green light. |

Scientific reports identify their graph, model and scoring contract. CI quality,
live integration and research jobs can produce different fitted model bytes;
their certificates must be replayed with the artifacts from the job that created
them. The [release guide](releasing.md) explains retained archives, checksums and
independent replay. The [reproduction guide](reproducibility.md) distinguishes
the committed reference from a fresh fit.

The six browser scenarios exercise actual checkbox changes, form submission,
details expansion, navigation and source links, a byte-exact certificate
download, Swagger execution and ReDoc navigation. An isolated negative control
that restores the old navigation selector fails: the checkbox cannot change.
This verifies that the regression gate detects the original interaction bug.
Current local checks do **not** establish a new Docker/Neo4j/GDS/provider run;
retain the final matching CI artifact when that run completes.

### Local verification on 2 November 2026

The README's **93.08% coverage** badge is a dated local measurement for tested
commit [`a35836be9d837f6741f886036070959469575616`](https://github.com/Azzbee/ariadne-bio/commit/a35836be9d837f6741f886036070959469575616),
recorded at **08:29 UTC on 2 November 2026**. The
[retained verification summary](evidence/local-verification-2026-11-02.json)
records **744 Python**, **170 frontend** and **6 Chromium** checks passing with
no failures or skips; **13 live-service tests were deselected** from this local
run. Coverage combines **4,149 of 4,419 executable lines** and **1,167 of 1,292
branches**: `(4,149 + 1,167) / (4,419 + 1,292) = 93.08%` after rounding.

The summary and underlying coverage XML, JUnit reports and logs are retained in
the verification archive. The **build / test** badge links to the actual remote
workflow; its run and commit remain the authority for Docker image builds and
live Neo4j/GDS/provider verification. Subsequent documentation-only changes do
not turn this dated result into a new execution claim.

## Run the complete application

Requirements: Git, Make, Python 3 and Docker with Compose v2. See the
[deployment guide](deployment.md) for memory/disk expectations and provider
configuration. From a fresh clone:

```bash
git clone https://github.com/Azzbee/ariadne-bio.git
cd ariadne-bio
make help
make docker-run
docker compose ps
curl --fail http://localhost:8080/api/health
```

To reproduce the sealed baseline specifically, run `git checkout v1.4.0` before
startup. For v1.4.1, use the complete source archive or check out the exact
commit in its `release-manifest.json` once that commit is public. Cloning the
repository alone does not select an unpublished submission candidate.
Prepare large downloads before a timed demonstration. `make docker-run` creates
private local credentials, prepares the checksummed graph, launches Neo4j/GDS,
FastAPI and Nginx, and prepares the configured local language model.

| Surface | Address or command |
| --- | --- |
| Application | `http://localhost:8080` |
| Swagger/OpenAPI | `http://localhost:8080/docs` |
| Neo4j Browser | `http://localhost:7474` — username `neo4j`; password is in the private local `.env`. |
| Health and live backend | `curl --fail http://localhost:8080/api/health` |
| Live logs | `make docker-logs` |
| Stop while retaining data | `make docker-stop` |

`make docker-core` runs the three core services with deterministic planning
unless a provider URL is configured. For core-only use after upgrading, clear
an old `ARIADNE_LLM_BASE_URL=http://ollama:11434/v1` value in the preserved `.env`.
The full `make docker-run` command supplies its own local-model connection.
The agent's response status, mode, tool trace and citations identify what
actually executed. The browser-only research
edition identifies recorded results; it is a convenient inspection artifact,
while the Compose application supplies the live Neo4j/GDS/LLM demonstration.

## Reproduce the notebook and tests

With Python 3.11+ and Node.js 18+ available, these commands preserve the retained
model and matching historical research artifacts:

```bash
make install
make prepare-data
make lint
make test
make notebook
```

`make notebook` writes `demo.executed.ipynb` after checking the graph, model,
evaluation and audit report identities. Use `make notebook-refit` in a disposable
checkout for a fresh fit with newly computed notebook evidence.

To include the exported-browser-case frontend tests, run `make snapshot` before
`make test`. Those tests explicitly report skips when no generated snapshot is
present. Snapshot export is separate from the reference notebook, which does
not require it; release verification should include the complete browser cases.

To run the six actual Chromium scenarios, use Node.js 20+ and install the locked
development tools and browser once:

```bash
cd frontend
npm ci --ignore-scripts
npx playwright install --with-deps chromium
cd ..
make test-browser
```

The browser gate requires the prepared graph, retained model and generated
snapshot. It launches its own isolated deterministic API and static server.

With the full stack running and its local credentials available, run the real
database and provider checks separately:

```bash
make test INTEGRATION=1
make test-llm
make smoke
```

The integration option includes genuine Neo4j/Cypher/GDS tests and fails if the
requested database is unavailable. The LLM suite requires actual provider
inference for successful requests; deterministic fallback is not a pass.
The smoke run checks the live HTTP workflow, certificate replay and rejection
of altered certificate claims. [Deployment](deployment.md) explains alternate
ports, database credentials and external-provider configuration.

To demonstrate the distinct **invalid LLM output** requirement reproducibly:

```bash
.venv/bin/python -m pytest -q tests/test_agent.py \
  -k invalid_model_outputs_fail_closed_before_scientific_tools
```

This is a disclosed fault-injection test: seven controlled provider responses,
including malformed JSON and an unauthorized Cypher field, must be rejected
before ranking executes. It complements the actual successful live-provider
request; it is not presented as a model spontaneously producing those responses.

## Human evidence and hand-in

The registered team is **Adam Zeraiki and Lina Oumhand**. The actual team lead
is unconfirmed in this record. Registration and AI-generated implementation do
not establish balanced contributions or one substantial merged PR per member.
Each teammate must understand the submission and identify the decisions,
corrections and reviews they actually performed. See [authorship](authorship.md)
and the [defense guide](defense_guide.md).

The instructor's 22 October 2026 submission email requires:

1. A public GitHub repository containing the complete project.
2. A video of at most ten minutes showing the project interface **and code**.
3. The repository and video submitted through Moodle.
4. The repository URL entered in the project information spreadsheet.

The signed-in Moodle assignment, inspected on **2 November 2026**, gives the
deadline as **Monday 2 November 2026 at 23:59 Europe/Paris**. Its upload form
accepts up to **20 files**, each at most **100 MB**, and all file types. The
current **15.34 MB** video fits that limit. The form has file submissions; a
short PDF containing the public repository and release links can accompany the
video. The instructor's alternative of a PDF with a public Drive video link is
available if a different video exceeds the limit.

The project spreadsheet's repository field is **completed and verified**. Moodle
still reports **No submissions**, with no last-modified timestamp: the upload
form was inspected and cancelled, and final submission awaits the team's
explicit green light. Private sheet links and mailbox details are absent here.

Any synthetic narration or edited/recorded sequence must be disclosed. A
technical walkthrough demonstrates the artifact; it does not certify a
teammate's understanding, contribution or independent review. The
[primary project specification](https://gist.github.com/bdallard/2ada69b40c3abfe3a7b3f6ed402b4b51#file-projects_spec-md),
updated 24 August 2026, remains the authority for technical assessment. Its
weights, potential penalties and required demonstrations are mapped in the
[rubric](rubric.md); no grade is self-awarded here.
