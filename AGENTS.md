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
- GET `/assessment/{disease_id}/{compound_id}?exclude=INTERACTS`
  => `{schema_version,disease,compound,known_treatment,excluded,model,
  baseline,current,delta,decomposition,interpretation}`. Both states include
  `{supported,rank|null,score,score_status,logit,evidence_count,features}`.
  `decomposition` has the saved intercept and ordered signed feature terms;
  intercept + contributions reconstructs the logit. Unsupported pairs remain
  inspectable with a diagnostic score and no supported rank.
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
- POST `/agent` body `{question, disease_id?, compound_id?, exclude:[]}` =>
  `{status:"complete"|"rejected"|"clarification",answer, disease?, compound?, assessment?, candidates:[],
  evidence?, citations:[], trace:[{step,tool,status,summary}],
  mode:"llm"|"deterministic", suggestions:[], disclaimer}`.
- GET `/similar/{compound_id}?limit=10` => `{compound,algorithm,items}`.
- GET `/algorithms/{disease_id}?limit=10` => GDS or exact local algorithm results,
  explicit execution backend. Never label local execution as GDS.
- GET `/provenance` => dataset manifest, citation, source license policy.
- POST `/audit` body `{disease_id,compound_id,top_k:10,budget:2}` => versioned
  binding-envelope certificate with `scope`, `identity`, `baseline`, `results`
  for each budget, `proof` and `certificate_sha256`. All BINDS edges, including
  competitors, are eligible; the full graph is used independently of UI exclusions.
  Integer `budget` is 0..2 and `top_k` 1..100. The audit-only declared arithmetic
  contract must not change legacy rankings or assessment bytes. New certificates
  use `decimal80-binary64-v1`; historical scorer identities retain their original
  verifier semantics. Unknown scorer identities fail closed.
- POST `/audit/verify` body `{certificate:<complete response>}` =>
  `{status:"verified"|"invalid",valid,checks,errors,verification_method,replayed_witnesses}`.
  Verification recomputes the same-algorithm bound and independently replays
  witnesses by matrix edits; a content hash alone is never sufficient.
- GET `/provenance/groups?kind=source&q=&limit=30&offset=0` => observed BINDS
  source-label or imported PubMed groups, exact membership digests and annotation
  coverage. Catalog lookup works without a fitted model. Labels and references
  never imply independent corroboration, falsity or verified study dependency.
- POST `/provenance/audit` body `{disease_id,compound_id,top_k:10,budget:2,
  group_kind:"source",group_ids:null,protected_group_ids:[]}` => exact correlated
  group-withdrawal certificate. Explicit selections contain 1..16 distinct groups;
  PubMed requires a selection. All source groups are the default. Withdraw the
  union of BINDS records mentioning any withdrawn group; rerank all compounds
  jointly. Budgets are 0..2, `top_k` is 1..100. `results[].robust` combines supported
  rank and loss-of-support results. The `protection_plan` finds minimum-cardinality
  additional groups whose withdrawal must be excluded to block every failing
  scenario. This is a conditional assumption, never an optimal review or experiment.
- POST `/provenance/audit/verify` accepts a complete group certificate and separately
  reconstructs the scenario table, protection optimum and matrix witnesses. The
  shared offline `scripts.verify_audit` CLI dispatches the binding, provenance
  and joint certificate methods.
- POST `/mixed/audit` body `{disease_id,compound_id,top_k:10,group_budget:1,
  edge_budget:1,group_kind:"source",group_ids:null}` => exact joint frontier for
  up to one selected provenance group plus one surviving individual BINDS record.
  Both budgets are strict integers in 0..1; `top_k` is 1..100. Explicit group
  selections contain 1..16 unique IDs; PubMed requires an explicit selection.
  Default scope contains every observed source label. A residual record must
  survive the group withdrawal; all competitors change and overlap is counted
  once. Record and group budgets have distinct units. Result rows cover every
  `(group_budget,edge_budget)` pair within the requested rectangle, ordered by
  group budget then edge budget. Unsupported outcomes remain separate from
  worst supported ranks. No group protection assumptions are accepted.
- POST `/mixed/audit/verify` accepts a complete certificate, recomputes the
  conditional envelopes and independently replays the union of each witness's
  source-group records and residual record. Method `mixed-group-edge-envelope-v1`
  uses only `decimal80-binary64-v1`. The offline verifier dispatches all three
  methods. Separate audit success does not establish joint robustness.

## Data engine interface

`GraphEngine(data_dir: Path)` loads `graph.json`, `model.json`,
`evaluation.json` and manifest in processed directory. Exposes
`stats()`, `diseases(query='',limit=30,offset=0)`,
`rankings(disease_id,exclude=(),limit=20,offset=0)`,
`evidence(disease_id,compound_id,exclude=(),limit=12)`,
`assessment(disease_id,compound_id,exclude=())`,
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
