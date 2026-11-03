# Rubric evidence matrix

Start with the [submission guide](submission.md) for version identity, runnable
commands and verification status. This maps the instructor's **100-point rubric**
to inspectable evidence; the weights are not marks awarded to this project.
A configured check is not proof that a revision passed.

Primary source: Benjamin Dallard's
[project specification](https://gist.github.com/bdallard/2ada69b40c3abfe3a7b3f6ed402b4b51#file-projects_spec-md)
and [checklist](https://gist.github.com/bdallard/2ada69b40c3abfe3a7b3f6ed402b4b51#file-project_checklist-md),
updated 24 August 2026 and checked on 2 November 2026.
The [Moodle assignment](https://moodle.essec.fr/mod/assign/view.php?id=817798)
and instructor emails of 22–23 October 2026 govern hand-in details.

## Core infrastructure, database and API — 25

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| At least three Compose services | 2 | [Compose](../docker-compose.yml): Neo4j, API, frontend; [full local-model startup](deployment.md) adds Ollama and its bootstrap. |
| Appropriate images and Dockerfiles | 2 | [API Dockerfile](../Dockerfile), [Neo4j/GDS image](../infra/neo4j.Dockerfile), [frontend Dockerfile](../frontend/Dockerfile). |
| Environment configuration without committed secrets | 2 | [.env.example](../.env.example), [.gitignore](../.gitignore), [private idempotent initialization](../infra/init_env.py). |
| Public container image and README link | 2 | [API package](https://github.com/Azzbee/ariadne-bio/pkgs/container/ariadne-bio-api), [frontend package](https://github.com/Azzbee/ariadne-bio/pkgs/container/ariadne-bio-frontend), [release verification status](submission.md#verification-and-version-status). |
| Clean Compose startup | 1 | [Startup procedure](submission.md#run-the-complete-application), health checks and commit-matched integration evidence. |
| Three or more labels and relationship types with properties | 3 | [Four biological types/families and retained properties](architecture.md#biological-evidence-model). |
| Two or more constraints | 2 | [Six ID uniqueness constraints](architecture.md#properties-constraints-and-indexes), [importer](../app/neo4j_repository.py), [integration assertions](../tests/test_neo4j_integration.py). |
| Relevant indexes | 2 | [Identity/name index rationale](architecture.md#properties-constraints-and-indexes) and [measured query plans](../reports/query_optimization.json). |
| Ingestion script | 2 | [Preparation](../scripts/prepare_data.py), [Neo4j ingestion](../scripts/load_neo4j.py), [import identity tests](../tests/test_neo4j_identity.py). |
| Documented dataset | 1 | [Data sources](data_sources.md) and [checksummed manifest](../data/processed/manifest.json). |
| Four endpoints including three advanced queries | 2 | [API contract](api.md): evidence paths, similarity, algorithms, rankings and challenge. |
| Pydantic validation | 2 | [Request/response schemas](../app/schemas.py) and [invalid-input API tests](../tests/test_api.py). |
| Working Swagger | 1 | Running stack: `http://localhost:8080/docs`; OpenAPI checks in [API tests](../tests/test_api.py). |
| Meaningful error handling | 1 | [API tests](../tests/test_api.py): unknown entity, invalid input and unavailable graph/report behavior. |

## Advanced graph and agent features — 27

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| Pathfinding or graph algorithms in two endpoints | 4 | [Typed paths, personalized PageRank and target similarity](api.md); [Neo4j/GDS implementation](../app/neo4j_repository.py). |
| Complex pattern matching | 3 | [Three bounded biological metapaths](architecture.md#three-path-templates), including distinct pathway genes. |
| WITH, UNWIND, subqueries and aggregations | 2 | [Repository queries](../app/neo4j_repository.py): batched ingestion, path collection, projection and similarity. |
| Query optimization | 5 | Parameterized, bounded queries; [PROFILE comparison](../reports/query_optimization.json); [performance explanation](defense_guide.md#queries-and-performance). |
| GDS projection and two algorithms | 2 | [Evidence/target projections and PageRank/node similarity](../app/neo4j_repository.py); [real database tests](../tests/test_neo4j_integration.py). |
| Machine-learning workflow | 3 | [Evaluation pipeline](../scripts/evaluate.py), [saved split and held-out results](../data/processed/evaluation.json), [model card](model_card.md). |
| LangGraph/GraphRAG tool workflow | 4 | [Compiled agent graph](../app/agent.py), [live-provider checks](../tests/test_llm_live.py), [actual execution evidence](submission.md#verification-and-version-status). |
| LLM guardrails, fact/hypothesis distinction and evaluation | 4 | [Typed plans and both validation boundaries](architecture.md#agent-control-flow), [seven invalid-provider-output cases](../tests/test_agent.py), [demonstration procedure](demo_script.md#provider-output-rejection-to-demonstrate). |

## Architecture, documentation and code — 16

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| Graph schema diagram | 2 | [README schema](../README.md#graph-schema) and [detailed schema](architecture.md). |
| System diagram with services, ports and data flow | 2 | [README architecture](../README.md#services-and-data-flow) and [runtime responsibilities](architecture.md#runtime-responsibilities). |
| Modeling rationale and anti-genericity appendix | 3 | [Comparison embedded in README](../README.md#modeling-and-anti-genericity-appendix), [baseline prompt and full rationale](anti_genericity.md). |
| Complete README | 3 | [Setup, API examples, screenshots, dataset, diagrams and assessment navigation](../README.md). |
| Exploration/visualization notebook | 2 | [Executed notebook](../demo.ipynb), [retained-model and fresh-fit reproduction paths](reproducibility.md). |
| Pylint configuration, score ≥9.5, Make target | 2 | [.pylintrc](../.pylintrc), [make lint](../Makefile), [actual run evidence](submission.md#verification-and-version-status). |
| Python structure/style | 1 | Typed modules under [app](../app), [Black and CI quality gate](../.github/workflows/ci.yml). |
| Docstrings | 1 | Public modules/functions in [app](../app), [scripts](../scripts) and [infra](../infra). |

## Automation — 3

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| Main Make commands | 1 | [Makefile](../Makefile): `help`, `install`, `run`, `docker-run`, `test`, `lint`, `clean`. |
| Functional commands and clear help | 1 | Actual command execution, [infrastructure tests](../tests/test_infrastructure.py) and [submission guide](submission.md). |
| Commands documented | 1 | [README reproduction](../README.md#reproduce-and-verify), [deployment](deployment.md) and [notebook reproduction](reproducibility.md). |

## Tests — 10

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| Unit, API and Neo4j tests | 3 | [Test suite](../tests): independent graph math, API execution and genuine database tests. |
| Container health tests | 2 | [Compose health checks](../docker-compose.yml), [fresh-stack smoke checks](../infra/smoke.py). |
| Cypher tests through Make | 2 | `make test INTEGRATION=1` includes the live Neo4j/Cypher/GDS suite; [configuration](deployment.md) is required and unavailable integration services fail the run. |
| Coverage ≥60% | 2 | CI coverage enforcement and the generated coverage report for the tested revision; see [verification status](submission.md#verification-and-version-status). |
| Passing suite and report | 1 | Commit-matched CI results and retained JUnit artifacts in the [verification record](submission.md#verification-and-version-status). |

## Engineering practices — 9

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| Lint on push or PR | 1 | [CI quality job](../.github/workflows/ci.yml). |
| Test workflow with coverage | 1 | [CI quality/integration jobs](../.github/workflows/ci.yml). |
| Build/test/coverage status | 1 | [README CI badge](../README.md) links to the actual workflow; revision-specific coverage is in retained verification evidence. Historical coverage is labeled historical. |
| At least two constructive review comments per PR | 1 | **Human evidence requires confirmation:** [actual PR/review history](https://github.com/Azzbee/ariadne-bio/pulls). Automated text is not presented as independent teammate review. |
| Reverse proxy or authentication | 3 | [Nginx configuration](../nginx.conf), loopback development ports, bounded requests and server-side provider credentials. |
| EXPLAIN/PROFILE index demonstration | 2 | [Measured optimization report](../reports/query_optimization.json) and [demonstration](demo_script.md). |

## Git and team collaboration — 10

| Criterion | Points | Inspectable evidence |
| --- | ---: | --- |
| Two active branches and feature workflow | 2 | [Actual branches](https://github.com/Azzbee/ariadne-bio/branches), [merged implementation PR #1](https://github.com/Azzbee/ariadne-bio/pull/1) and [PR history](https://github.com/Azzbee/ariadne-bio/pulls). |
| Appropriate .gitignore | 1 | [Ignore policy](../.gitignore); secrets and reproducible caches stay outside source control. |
| Balanced substantive contributions | 3 | **Not established by registration:** actual history and individual work must support the claim; see [authorship](authorship.md). |
| Substantial merged PR per member | 3 | **Not established for every registered member:** link each person's real substantive work after it exists. |
| Clear commit messages | 1 | [Actual commit history](https://github.com/Azzbee/ariadne-bio/commits/main). |

The registered team is Adam Zeraiki and Lina Oumhand; the actual team lead remains
unconfirmed in this record. The observed source history does not demonstrate
balanced work by both people. The specification also describes possible
individual penalties for very low contributions or missing substantial PRs.
Code completeness does not resolve these requirements. Each student must be
able to defend the work, and reviews and attribution must reflect real activity.

## Submission package

The instructor's 22 October 2026 email requires a public complete GitHub
repository and a video of **at most ten minutes** presenting the application
interface and code, submitted through Moodle. The project information spreadsheet
must contain the repository URL. If the video is too large, the email permits an
uploaded PDF containing a public Drive link. The 23 October email confirms a
2 November deadline; verify the precise cutoff and final submission receipt in
Moodle.

The primary specification additionally requires a successful agent request and
rejection of invalid **LLM output** during demonstration. The
[current demonstration script](demo_script.md) covers both, with fault injection
clearly separated from genuine provider inference. The [submission guide](submission.md)
records which version, video and hand-in evidence are actually available.
