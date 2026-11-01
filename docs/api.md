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
| `POST /api/audit` | Exact worst supported rank and possible loss of support under a global budget of up to two BINDS-edge deletions |
| `POST /api/audit/verify` | Recompute a certificate's bounds and independently replay its witnesses; reject altered or mismatched claims |
| `POST /api/agent` | Resolve the question and optional selected entities, run bounded tools and return a grounded brief |
| `GET /api/algorithms/{disease_id}?limit=10` | Graph proximity analysis with its actual execution backend |
| `GET /api/similar/{compound_id}?algorithm=gds&limit=10` | Compound target-neighborhood similarity; default `algorithm=cypher` |
| `GET /api/evaluation` | Recorded evaluation protocol, metrics, intervals and failures |
| `GET /api/provenance` | Dataset identity, source information and license policy |
| `GET /api/provenance/groups?kind=source&q=&limit=30&offset=0` | Imported binding-record source or PubMed groups, membership digests and annotation coverage |
| `POST /api/provenance/audit` | Exact correlated group withdrawals, original shortlist and minimum conditional protection sets |
| `POST /api/provenance/audit/verify` | Recompute the complete group certificate and independently replay its matrix witnesses |
| `POST /api/mixed/audit` | Exact frontier for up to one provenance group plus one additional surviving binding record, including all competitors |
| `POST /api/mixed/audit/verify` | Recompute the joint frontier and independently replay the complete group-and-record union |

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

## Exact global binding audit

```bash
curl -X POST 'http://localhost:8080/api/audit' \
  -H 'Content-Type: application/json' \
  -d '{"disease_id":"Disease::DOID:10652","compound_id":"Compound::DB00184","top_k":10,"budget":2}' \
  --output binding-audit.json

python -c 'import json,sys; print(json.dumps({"certificate": json.load(sys.stdin)}))' \
  < binding-audit.json | curl -X POST 'http://localhost:8080/api/audit/verify' \
  -H 'Content-Type: application/json' --data-binary @-
```

`budget` is an integer from zero to two; `top_k` is an integer from one to 100.
The request accepts only those fields plus the two entity IDs. Extra fields,
including family exclusions, are rejected. The audit always starts from the
complete evidence graph and can withdraw recorded BINDS edges from the selected
compound **or any competitor**. It never changes the fitted model or stored graph.

| Field | Meaning |
| --- | --- |
| `method`, `schema_version` | Algorithm and certificate format identity |
| `scope` | BINDS deletion, all recorded binding edges, eligible-edge and candidate counts, competitor inclusion |
| `identity` | Dataset/graph/model SHA-256 values and the canonical audit scorer identifier |
| `baseline` | Declared audit score, logit, supported status and rank, and counts. Historical float64 certificates also retain recorded legacy comparison fields; new decimal/binary64 certificates omit them. |
| `results` | One result for each budget from zero through the requested limit |
| `results[].worst_supported_rank` | Exact largest supported rank attainable anywhere in the allowed deletion space, or null if no supported state exists |
| `results[].unsupported_attainable` | Whether some allowed deletion leaves the focus with no supporting paths |
| `results[].top_k_robust` | True only when every allowed state is supported and the worst supported rank is at most `top_k` |
| `results[].focus_only_worst_rank` | Restricted comparison with only the selected compound's edges eligible for removal |
| `results[].competitor_rank_gap` | Global minus focus-only worst rank; null when no supported state exists |
| `results[].rank_witness`, `unsupported_witness` | Concrete removed record IDs and available provenance, resulting focus state and changed compounds; null when inapplicable |
| `minimum_failure_budget` | Earliest tested budget that loses top-k membership/support; zero is possible for an initially off-list or unsupported focus |
| `robust_through_budget` | Largest contiguous tested robust budget, or null if the baseline is not robust |
| `proof.local_states_evaluated` | Enumerated per-compound states used to construct local envelopes |
| `proof.covered_global_states` | Number of globally allowed deletion subsets for the requested budget |
| `proof.search_budget` | Envelope construction limit; the implementation prepares and caches all local budgets through two even for a smaller request |
| `proof.envelope_bounds_sha256` | Digest of the local envelope bounds and attaining local states |
| `certificate_sha256` | Deterministic JSON digest of the complete certificate excluding this field |

Ranks use the declared audit score descending and compound ID ascending for
ties. New certificates identify `decimal80-binary64-v1`; historical
`float64-fixed-order-v1` certificates retain their original arithmetic identity.
The existing ranking endpoint keeps its own scorer. New certificates omit
`legacy_score`, `legacy_rank`, `score_difference`, and `rank_agrees_with_legacy`;
absence of these fields makes no claim about explorer rank or agreement.
Verification dispatches by the declared scorer and rejects unknown identities.
A top-k guarantee here is conditional on the graph, frozen
model, scorer, candidate universe and allowed deletion family. It is not a
clinical claim or a probability that the shortlist is correct.

Verification accepts `{ "certificate": <complete audit object> }`. It returns
`{status,valid,checks,errors,verification_method,replayed_witnesses}`. An invalid
certificate produces `status="invalid"`, `valid=false` and error details; this
is a handled HTTP 200 verification result, not a server success claim. A valid
content hash alone is insufficient: recomputed identities, bounds and every
distinct witness must match. Optimality is recomputed with the same envelope
algorithm; witness replay uses independent edited-matrix calculations. Exhaustive
small-graph tests are the separate maximality oracle.

Malformed/unbounded requests receive HTTP 422, unknown entities 404, and a
missing fitted model 503. Verification rejects nonfinite JSON values and
certificate payloads above 256 KiB. The Nginx request-size bound also applies.
See the [formal proof and limitations](binding_audit_proof.md).

## Shared provenance-group audit

```bash
curl 'http://localhost:8080/api/provenance/groups?kind=source&limit=100'

curl -X POST 'http://localhost:8080/api/provenance/audit' \
  -H 'Content-Type: application/json' \
  -d '{"disease_id":"Disease::DOID:7148","compound_id":"Compound::DB00786","top_k":10,"budget":1}' \
  --output provenance-audit.json

python -m scripts.verify_audit provenance-audit.json --data-dir data/processed
```

The example selects Marimastat and rheumatoid arthritis. The default group
universe contains every imported BINDS source label (14 in the pinned dataset).
`budget` counts groups, not records. A withdrawn group removes **every binding
record mentioning it**, including records carrying other labels. Overlapping
memberships remove a record only once. The fixed model reranks the complete
compound universe jointly. Other evidence-family controls do not change this
audit's baseline.

| Request field | Contract |
| --- | --- |
| `disease_id`, `compound_id` | Exact typed identifiers; missing entities receive 404 |
| `top_k` | Strict integer 1..100; default 10 |
| `budget` | Strict integer 0..2; default 2 |
| `group_kind` | `source` or `pubmed`; default `source` |
| `group_ids` | An explicit list of 1..16 unique IDs, or omitted/null for the complete source-label universe |
| `protected_group_ids` | Unique IDs within the selected universe; these group actions are assumed unavailable for withdrawal |

A PubMed audit requires explicit IDs such as `"pubmed:22037378"`. The catalog
supports substring search, a maximum page size of 100 and an offset bounded by
the catalog implementation. It inventories imported annotations, including
records missing the selected annotation kind; it does not verify the cited
paper or infer which source independently supports a consolidated record.

| Certificate field | Meaning |
| --- | --- |
| `scope.group_ids`, `scope.groups` | Exact selected universe, label names, complete membership digests and record/compound counts |
| `scope.protected_group_ids` | Explicit conditional exclusions from the withdrawal actions |
| `identity.group_map_sha256` | Digest binding the complete imported group membership map |
| `results[].scenario_count` | All allowed group subsets for that budget after protection exclusions |
| `results[].worst_supported_rank`, `unsupported_attainable` | Exact joint-rank bound and separately attainable loss of every supporting path |
| `results[].robust` | Every allowed scenario stays supported and within the requested top-k |
| `results[].rank_witness`, `unsupported_witness` | Attaining group IDs, complete union digest/count, affected-compound count, at most 12 actual record previews and focus before/after |
| `protection_plan` | Minimum number of additional unavailable groups, a representative set, exact optimum-set count and up to 12 alternatives |
| `shortlist` | Original top-k outcomes under the same allowed scenario family, capped at 20 displayed rows with `shortlist_truncated` |
| `proof` | Complete scenario-table digest, construction budget and evaluated/covered scenario counts |

Protection is a mathematical condition: the listed group actions cannot occur.
Reviewing a group does not establish that condition or that its records are true.
A protected group's overlapping record can still be withdrawn through another
unprotected group. The optimum minimizes group count, not cost, reviewer time or
experimental value. An unsupported or off-list baseline yields
`status="impossible_baseline"`; a robust scope needs no additional groups.

Verification accepts `{ "certificate": <complete object> }` with the same 256 KiB
finite-JSON bound as the individual-record verifier. It checks identities, all
recomputed claims including the protection optimum, and independent matrix
witness replays. Correctly rehashing a fabricated result does not make it valid.
The HTTP verification response distinguishes a completed invalid verdict from
transport errors. The CLI exits zero only for a verified certificate.

All audit verifiers require the exact matching graph and fitted model. Docker can fit
a separate model from the frozen research edition; retained live-container
artifacts identify the model used for its certificates. See the
[group-audit guide](provenance_audit.md), [proof](provenance_audit_proof.md) and
[deployment instructions](deployment.md). Scientific validity and clinical
efficacy remain outside these finite model guarantees.

## Joint source-group and individual-record audit

```bash
curl -X POST 'http://localhost:8080/api/mixed/audit' \
  -H 'Content-Type: application/json' \
  -d '{"disease_id":"Disease::DOID:7148","compound_id":"Compound::DB00786","top_k":10,"group_budget":1,"edge_budget":1}' \
  --output joint-audit.json

python -c 'import json,sys; print(json.dumps({"certificate": json.load(sys.stdin)}))' \
  < joint-audit.json | curl -X POST 'http://localhost:8080/api/mixed/audit/verify' \
  -H 'Content-Type: application/json' --data-binary @-

python -m scripts.verify_audit joint-audit.json --data-dir data/processed
```

The source group withdraws every BINDS record carrying its selected annotation.
The additional record must survive that withdrawal. Overlapping membership
never removes a record twice, and the remaining record can belong to the focus
or any competitor. Unannotated records and records with unselected annotations
remain eligible for the individual-record operation. All paths and ranks are
computed from the unmodified full graph followed by those declared changes;
the explorer's evidence-family switches do not alter the audit scope.

| Request field | Contract |
| --- | --- |
| `disease_id`, `compound_id` | Exact typed entity IDs, each at most 180 characters |
| `top_k` | Strict integer 1..100; default 10 |
| `group_budget` | Strict integer 0 or 1; default 1 |
| `edge_budget` | Strict integer 0 or 1; default 1 |
| `group_kind` | `source` or `pubmed`; default `source` |
| `group_ids` | 1..16 unique, matching-kind group IDs; omitted/null selects all observed source labels |

PubMed requests require an explicit group selection. Unknown groups, duplicate
IDs, booleans or strings in place of integer budgets, family exclusions,
protection assumptions and other extra request fields are rejected with HTTP
422. Missing entities receive 404 and a missing fitted model receives 503.
Use `/api/provenance/groups` to discover the available imported annotations.

The response declares `method="mixed-group-edge-envelope-v1"`,
`schema_version="1.0"` and `identity.scorer="decimal80-binary64-v1"`.
`results` contains every budget cell from `(0,0)` through the requested rectangle,
ordered first by group budget and then by edge budget. The default returns
`(0,0)`, `(0,1)`, `(1,0)`, `(1,1)`. Each cell covers **at most** its two budgets.
The units remain separate: one group can contain thousands of records.

| Certificate field | Meaning |
| --- | --- |
| `scope.group_ids`, `scope.groups` | Selected group universe and exact membership metadata |
| `scope.eligible_edge_count`, `scope.candidate_count` | Global record and compound universes |
| `identity` | Exact dataset, graph, fitted model, group map and scorer identities |
| `baseline` | Unmodified canonical audit score, supported status, rank and path counts |
| `results[].group_budget`, `results[].edge_budget` | The two limits for this frontier cell |
| `results[].worst_supported_rank` | Largest attainable supported rank; null if no supported state exists |
| `results[].unsupported_attainable` | Whether some permitted joint edit removes every supporting path |
| `results[].robust` | Every allowed state remains supported and within the requested top-k |
| `results[].rank_witness`, `unsupported_witness` | An attaining group/record action, or null when inapplicable |
| `proof.conditional_slice_count` | Number of constructed group-conditioned cases |
| `proof.local_states_evaluated` | Compound-local score states constructed across those cases |
| `proof.covered_action_representations` | Covered group/residual-record action representations; different actions can produce the same edited graph |
| `proof.envelope_table_sha256`, `proof.conditional_slices` | Complete conditional-envelope identity and per-case accounting |
| `certificate_sha256` | Deterministic digest of the full certificate excluding this field |

Each witness contains `group_ids`, `residual_edge_ids`, the complete removed-union
count and digest, the affected-compound count, at most six actual record previews,
an explicit truncation flag, and the focus state before and after the edit.
The preview is not the complete withdrawn record list. Replay reconstructs the
union from the identified graph and group map, then applies the residual deletion.

Verification accepts the complete certificate in the standard
`{"certificate": ...}` envelope, with the same 256 KiB finite-JSON bound. It
recomputes the entire frontier and separately replays distinct witnesses with
edited matrices. Unknown arithmetic identities and correctly rehashed false
claims are rejected. A completed invalid verdict is HTTP 200 with `valid=false`;
malformed or oversized request envelopes are transport validation errors.

Passing the two separate axes does not establish joint robustness. Conversely,
observing a joint failure is a property of this finite fixed-model stress test,
not biological synergy, a source-error probability or a clinical prediction.
See the [user guide](mixed_audit.md), [proof](mixed_audit_proof.md) and
[research comparison](research_atlas.md).

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
JSON. Its manifest identifies the dataset, fitted model, seven included disease
cases and sixteen exclusion configurations per case. Assessments are exported
for the union of displayed candidates so a selected compound remains inspectable
when its rank changes. The guide is deterministic and its trace says that no LLM
was called. Use the live application for diseases or compound evidence outside
the recorded selection.

V1.2 also exports binding certificates for recorded compounds at `top_k` values
1, 5 and 10 and budgets zero, one and two. Export-time verification is recorded.
The static interface can inspect those objects and check their recorded identity;
it cannot recompute graph optimality in the browser. A matching live API can
reverify an exported certificate. Unsupported parameter combinations require the
live application rather than a fabricated static result.

V1.3 adds source-group presets at top ten and group budgets one and two. V1.4
adds joint source/record presets at top ten with both budgets one, retaining
the complete four-cell frontier for every exported compound. A recorded
verification must identify the exact certificate and graph/model snapshot.
Explicit PubMed selections, custom protection assumptions and unexported scopes
require the live API; a pair of separate-axis certificates cannot stand in for
a joint certificate. The landing page's three-step illustration remains an
explicitly versioned v1.3 recorded example.

The static client checks raw case bytes against the manifest's length/SHA-256
descriptors before parsing and caching, and requires matching certificate
dataset/model/graph identities. Those are consistency checks against the served
manifest, not an independent digital signature or a proof of optimality.

The seventh recorded case, vascular cancer, was added after the all-disease
benchmark to illustrate a measured competitor-only failure for Nifedipine.
Selecting that illustration did not change the benchmark's 137-disease cohort.
The certificate hash accepts equivalent JSON number spellings such as `0` and
`0.0`, preserves all nonintegral score values exactly, and rejects unsafe integers
or nonfinite values. See the [checksum convention](binding_audit_proof.md#verification-and-limits).
