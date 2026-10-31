# API contract and examples

The live API is rooted at `/api`. Interactive request and response schemas are at
http://localhost:8080/docs through the standard Compose reverse proxy. Namespace
qualified identifiers refer to exact entities, not display names. Evidence-family
exclusions are drawn only from `BINDS`, `ASSOCIATES`, `INTERACTS` and `PARTICIPATES`.

## Main routes

| Route | Purpose |
| --- | --- |
| `GET /api/health` | Dataset/backend state and configured agent mode; each agent response reports its actual mode |
| `GET /api/diseases?q=asthma&limit=30&offset=0` | Search and paginate the disease dictionary |
| `GET /api/rankings/{disease_id}?exclude=INTERACTS&limit=12&offset=0` | Ordered graph-supported compound ranking under one exclusion set |
| `GET /api/assessment/{disease_id}/{compound_id}?exclude=INTERACTS` | Exact baseline/current assessment for any valid pair, including an unsupported pair |
| `GET /api/evidence/{disease_id}/{compound_id}?exclude=INTERACTS&limit=12` | Bounded displayed paths plus full path counts and retained source metadata |
| `POST /api/challenge` | Compare rankings using the same model after selected evidence removal |
| `POST /api/agent` | Resolve the question and optional selected entities, run bounded tools and return a grounded brief |
| `GET /api/algorithms/{disease_id}?limit=10` | Graph proximity analysis with its actual execution backend |
| `GET /api/similar/{compound_id}?algorithm=gds&limit=10` | Compound target-neighborhood similarity; default `algorithm=cypher` |
| `GET /api/evaluation` | Recorded evaluation protocol, metrics, intervals and failures |
| `GET /api/provenance` | Dataset identity, source information and license policy |

Ranking and algorithm limits are bounded to 100, evidence display to 30, and
challenge results to 50. Disease pagination allows at most 137 per request.
Malformed inputs or unsupported exclusion families receive HTTP 422; missing
entities receive 404; unavailable graph queries receive 503.

## Selected-compound assessment

```bash
curl 'http://localhost:8080/api/assessment/Disease::DOID:10652/Compound::DB00184?exclude=INTERACTS'
```

This asks for Nicotine and Alzheimer's disease with gene-interaction evidence
removed. The response preserves the same pair in both states:

| Field | Meaning |
| --- | --- |
| `disease`, `compound` | Exact entity identities |
| `known_treatment` | Lookup in the separate recorded treatment table, never a predictive feature |
| `model` | Fitted model name, available version, model SHA-256 and dataset SHA-256 |
| `baseline` | All evidence enabled, regardless of the previous UI state |
| `current` | The requested exclusion set |
| `baseline/current.supported` | Whether this pair has any surviving evidence paths |
| `baseline/current.rank` | Rank among graph-supported compounds, or null when unsupported |
| `baseline/current.score_status` | `supported_retrieval` or `unsupported_diagnostic` |
| `baseline/current.score`, `logit` | Finite fixed-model output and its pre-sigmoid linear predictor |
| `baseline/current.features` | Exact direct, interaction and shared-pathway counts |
| `delta` | Current minus baseline for score, logit and path count; baseline minus current for rank |
| `decomposition.features` | Eight ordered feature terms, including definitions, values, training means/scales, coefficients, standardized values and signed contributions before/after |
| `decomposition.intercept` | Saved intercept added once to the feature contributions |
| `interpretation` | The limits of the decomposition and unsupported-pair semantics |

Adding the intercept to all `contribution_before` terms reconstructs the baseline
logit. The `contribution_after` terms reconstruct the current logit. Applying the
sigmoid gives the corresponding score. The sum of `contribution_delta` terms is
the logit change. These identities hold within floating-point precision; the
terms are not causal attributions or clinical probabilities.

Excluding `BINDS` or `ASSOCIATES` removes all three supported path patterns. The
assessment still returns the selected pair and its diagnostic score, with
`current.supported=false` and `current.rank=null`. This is distinct from an invalid
entity. The model card describes [the exact mathematics](model_card.md#exact-selected-compound-explanation).

## Compound-aware agent

```bash
curl -X POST 'http://localhost:8080/api/agent' \
  -H 'Content-Type: application/json' \
  -d '{"question":"Explain Nicotine for Alzheimer disease.","disease_id":"Disease::DOID:10652","compound_id":"Compound::DB00674","exclude":["INTERACTS"]}'
```

The intentionally stale compound selection above is Galantamine. The explicitly
named Nicotine determines `compound`, `evidence.compound` and `assessment.compound`
in the result. A single explicit disease name similarly overrides the selected
disease. Multiple explicit names of the same entity type require clarification.
Without an explicit name, the supplied selection provides the focus.

`candidates` remains the correctly ordered top-K ranking for context; it is not
reordered to make the focused compound look better. The answer includes bounded
path citations and the actual LangGraph tool trace. `mode=llm` requires a
successful real planner invocation; `mode=deterministic` discloses fallback or
explicit deterministic operation. The provider proposes a validated plan; the
brief is composed from returned tool records. It does not supply model scores or
feature contributions.

The same request can be made with only a question and disease. `compound_id` is
optional. Explicit exclusions in the question, validated planner exclusions and
UI exclusions are merged. Unsafe write requests are rejected before graph tools
run. The request boundary is a research interface, not a clinical advice service.

## Frozen research edition

The static edition exposes the same JavaScript client interface through recorded
JSON. Its manifest identifies the dataset, fitted model, six included disease
cases and sixteen exclusion configurations per case. Assessments are exported
for the union of displayed candidates so a selected compound remains inspectable
when its rank changes. The guide is deterministic and its trace says that no LLM
was called. Use the live application for diseases or compound evidence outside
the recorded selection.
