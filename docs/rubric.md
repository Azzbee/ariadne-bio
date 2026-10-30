# Rubric evidence matrix

This maps the published coursework categories to inspectable artifacts. It is
an evidence index, not a self-awarded mark. Execution evidence must match the
submitted commit, and collaboration requirements require actual human work.

Sources: [Moodle assignment](https://moodle.essec.fr/mod/assign/view.php?id=817798)
and [project specification/checklist](https://gist.github.com/bdallard/2ada69b40c3abfe3a7b3f6ed402b4b51#file-projects_spec-md).

## Core infrastructure, database and API — 25

| Criterion | Points | Evidence |
| --- | ---: | --- |
| At least three Compose services | 2 | `docker-compose.yml`: Neo4j, API, frontend, optional local model |
| Appropriate images and Dockerfiles | 2 | `Dockerfile`, `infra/neo4j.Dockerfile`, `frontend/Dockerfile` |
| Environment configuration without committed secrets | 2 | `.env.example`, `.gitignore`, private idempotent `infra/init_env.py` |
| Public container image and README link | 2 | CI publish jobs, README package links, unauthenticated pull verification |
| Clean Compose startup | 1 | CI integration job, health checks and startup logs |
| Three or more labels/relationship types with properties | 3 | Four biological types/families, namespace IDs and source metadata |
| Two or more constraints | 2 | `app/neo4j_repository.py` schema and integration assertions |
| Relevant indexes | 2 | Entity identity and name indexes, query-plan report |
| Ingestion script | 2 | `scripts/prepare_data.py`, `scripts/load_neo4j.py`, idempotence tests |
| Documented dataset | 1 | `docs/data_sources.md`, checksum manifest |
| Four endpoints including three advanced queries | 2 | Evidence, similarity, algorithms and challenge routes |
| Pydantic validation | 2 | `app/schemas.py`, invalid-input API tests |
| Working Swagger | 1 | `/docs`, OpenAPI test |
| Meaningful error handling | 1 | 404 unknown entity, 422 invalid input, 503 graph/report failure |

## Advanced graph and agent features — 27

| Criterion | Points | Evidence |
| --- | ---: | --- |
| Pathfinding/graph algorithms in two endpoints | 4 | Typed paths, personalized PageRank and target similarity |
| Complex pattern matching | 3 | Three bounded biological metapaths |
| WITH, UNWIND, subqueries or aggregation | 2 | Batched ingestion, path collection and similarity queries |
| Query optimization | 5 | Parameterization, bounds, indexes, `reports/query_optimization.json` |
| GDS projection and two algorithms | 2 | Evidence/target projections, PageRank/node similarity, integration tests |
| Machine-learning workflow | 3 | `scripts/evaluate.py`, fixed split/model, held-out metrics and baselines |
| LangGraph/GraphRAG tool workflow | 4 | `app/agent.py`, compiled graph, live-provider execution report |
| Guardrails, fact/hypothesis distinction and evaluation | 4 | Typed plans, adversarial tests, traces, model card, rejection demonstration |

## Architecture, documentation and code — 16

| Criterion | Points | Evidence |
| --- | ---: | --- |
| Graph schema diagram | 2 | `docs/architecture.md` |
| System diagram | 2 | README and architecture document |
| Modeling rationale and anti-genericity appendix | 3 | `docs/anti_genericity.md` |
| Complete README | 3 | Setup, API examples, dataset, architecture and document links |
| Exploration/visualization notebook | 2 | Executed `demo.ipynb` and reproducible notebook runner |
| Pylint configuration, score >=9.5, Make target | 2 | `.pylintrc`, `make lint`, actual CI/local output |
| Python structure/style | 1 | Typed modules, formatter gate |
| Docstrings | 1 | Public modules, functions and rationale |

## Automation — 3

| Criterion | Points | Evidence |
| --- | ---: | --- |
| Main Make commands | 1 | `help`, `install`, `run`, `docker-run`, `test`, `lint`, `clean` |
| Functional commands and help | 1 | Actual target execution and infrastructure test |
| Commands documented | 1 | README and deployment guide |

## Tests — 10

| Criterion | Points | Evidence |
| --- | ---: | --- |
| Unit, API and Neo4j tests | 3 | Real graph math, FastAPI/LangGraph execution and Neo4j tests |
| Container health | 2 | Compose health checks, CI fresh-stack smoke |
| Cypher tests through Make | 2 | `make test-integration` and CI |
| Coverage >=60% | 2 | Coverage gate and generated report |
| Passing suite and report | 1 | Submitted commit's CI result and retained JUnit artifacts |

## Engineering practices — 9

| Criterion | Points | Evidence |
| --- | ---: | --- |
| Lint in CI | 1 | Quality job |
| Tests and coverage in CI | 1 | Quality/integration jobs |
| Status badges | 1 | Dynamic CI badge |
| At least two constructive comments per PR | 1 | Actual human review history |
| Reverse proxy or sensitive endpoint authentication | 3 | Nginx reverse proxy, internal services, no public write endpoint |
| EXPLAIN/PROFILE index demonstration | 2 | Measured query optimization report and demonstration |

## Git and team collaboration — 10

| Criterion | Points | Evidence |
| --- | ---: | --- |
| Two active branches and feature workflow | 2 | Actual repository branch/PR history |
| Appropriate .gitignore | 1 | Source ignore policy and no committed credentials |
| Balanced substantive commits | 3 | Actual human contribution history |
| Substantial merged PR per member | 3 | Actual teammate changes and reviewed merges |
| Clear commit messages | 1 | Repository history |

Automated implementation cannot certify a teammate's contribution, conduct
their oral defense or manufacture independent peer review. See
[authorship.md](authorship.md).

## Submission package

- Public repository with complete source and reproducible data pipeline.
- Video up to ten minutes showing the interface, code, commands and both a
  successful agent investigation and a rejected invalid request.
- Team spreadsheet repository link and Moodle submission.
- If the video exceeds Moodle's upload limit, the instructor's email permits a
  PDF containing a public Drive link.

The slide deck describes a 30% project component while Moodle calls this item
“Optional project.” The instructor's interpretation determines that weighting.
