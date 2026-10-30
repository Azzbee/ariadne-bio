# ARIADNE development contract

Build an honest, reproducible biomedical evidence investigator. Never fabricate
research results, source provenance, clinical validity, human contributions, or
verification. Imported graph relationships are recorded facts in Hetionet;
candidate rankings are hypotheses, never treatment advice.

## Ownership

- Root: API, agent, Neo4j repository, integration, GitHub and publication.
- Data agent: `app/graph_engine.py`, `scripts/prepare_data.py`, `scripts/evaluate.py`,
  scientific artifacts, data/model tests.
- Frontend agent: `frontend/` only, browser UI tests under `frontend/`.
- Infrastructure agent: Dockerfiles/Compose, Makefile, CI, documentation, notebook,
  packaging requirements and infra tests. Coordinate before editing root-owned files.

## Shared API (JSON)

All endpoints begin `/api`. Frontend must be adaptable via a single API module.
IDs are namespace-qualified strings, e.g. `Disease::DOID:...`.

- GET `/health` => `{status, graph_backend, dataset_ready, agent_mode, version}`.
- GET `/stats` => `{dataset, version, nodes, edges, node_counts, edge_counts,
  diseases, compounds, dataset_sha256, model, disclaimer}`.
- GET `/diseases?q=&limit=30&offset=0` => `{items:[{id,name}], total}`.
- GET `/rankings/{disease_id}?exclude=INTERACTS&limit=20&offset=0`
  => `{disease:{id,name}, candidates:[{id,name,rank,score,baseline_rank,
  rank_delta,known_treatment,features:{direct,interaction,pathway}, evidence_count}],
  total, excluded, model, interpretation, elapsed_ms}`.
  `exclude` comma-separated families in `BINDS,ASSOCIATES,INTERACTS,PARTICIPATES`.
- GET `/evidence/{disease_id}/{compound_id}?exclude=&limit=12`
  => `{disease, compound, nodes:[{id,name,label,url}],
  edges:[{id,source,target,type,sources,license}],
  paths:[{id,node_ids,edge_ids,metapath,weight}],
  counts:{direct,interaction,pathway}, total_paths, truncated, excluded}`.
- POST `/challenge` body `{disease_id, exclude:["INTERACTS"], limit:10}`
  => `{disease, excluded, before:[candidate], after:[candidate],
  changes:[{id,name,before_rank,after_rank,rank_delta,score_before,score_after}],
  explanation, elapsed_ms}`.
- GET `/evaluation` => report JSON including `metrics` (list of model rows),
  `protocol`, `split`, `examples`, `limitations`, `dataset_sha256`.
- POST `/agent` body `{question, disease_id?, exclude:[]}` =>
  `{status:"complete"|"rejected"|"clarification",answer, disease?, candidates:[],
  evidence?, citations:[], trace:[{step,tool,status,summary}],
  mode:"llm"|"deterministic", suggestions:[], disclaimer}`.
- GET `/similar/{compound_id}?limit=10` => `{compound,algorithm,items}`.
- GET `/algorithms/{disease_id}?limit=10` => GDS or exact local algorithm results,
  explicit execution backend. Never label local execution as GDS.
- GET `/provenance` => dataset manifest, citation, source license policy.

## Data engine interface

`GraphEngine(data_dir: Path)` loads `graph.json`, `model.json`,
`evaluation.json` and manifest in processed directory. Exposes
`stats()`, `diseases(query='',limit=30,offset=0)`,
`rankings(disease_id,exclude=(),limit=20,offset=0)`,
`evidence(disease_id,compound_id,exclude=(),limit=12)`,
`challenge(disease_id,exclude,limit=10)`, `similar(compound_id,limit=10)`,
`algorithms(disease_id,limit=10)`, `evaluation()`, `provenance()`.

Only evidence edges are used for graph features. TREATS and PALLIATES never enter
features, projections, cached graph statistics, or embeddings. Known treatments
are a separate factual lookup and a label set. Train/validation/test split before
model fitting. Exclusion recomputes features with the SAME fitted model.

## Quality

Use Python 3.11+, Pydantic validation, parameterized and bounded Cypher, genuine
LangGraph orchestration with read-only typed tools, meaningful tests, and lint.
No broad pylint suppressions to manufacture a score. Record actual commands and
results. Keep secrets and bulky raw data out of Git. Pin dataset checksum and
dependency versions. Do not create commits as Lina or invent peer reviews.
