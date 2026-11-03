# Defense guide

Use this to check understanding against the actual code and reports. Each
teammate should explain the decisions in their own words and identify their own
work. Memorizing an explanation or reading an AI-generated script does not
establish authorship. The [rubric](rubric.md) and [timed demonstration](demo_script.md)
map these topics to the instructor's requirements.

## The project in two sentences

ARIADNE helps researchers explore medicines that might be worth investigating
for another disease and inspect the biological evidence behind each suggestion.
It then checks which suggestions survive specified changes to that evidence,
including a shared source withdrawal combined with an individual record change.

## Graph and modeling decisions

**Why use a graph?** A useful explanation joins a compound, its targets, disease
genes and possibly an interaction or pathway. Typed paths let us distinguish
those explanations and identify exactly which records support them. A flat
ranking alone cannot show those dependencies. See the
[schema and rejected alternatives](anti_genericity.md).

**Why is a pathway a node rather than a string property?** Many genes can share
the same identifiable pathway, and pathway membership has its own relationships
and metadata. A node supports traversal between distinct genes without copying
the pathway's identity into unrelated free-text fields. A display name remains
a property; a stable, shared entity becomes a node.

**Why stable IDs and four evidence families?** Names collide or change. Qualified
IDs preserve source namespaces and make imports, joins and certificates
reproducible. `BINDS`, `ASSOCIATES`, `INTERACTS` and `PARTICIPATES` have different
roles; collapsing them into a generic association would obscure metapaths and
make evidence exclusions ambiguous. `Gene` retains Hetionet's gene/protein
meaning; a compound binding edge concerns the encoded protein.

**What is a metapath?** A sequence of entity and relationship types. ARIADNE uses
C–G–D, C–G–G–D and C–G–P–G–D. The interaction and pathway templates require
distinct gene positions; otherwise a supposed indirect explanation can repeat
direct gene overlap. [Exact definitions](architecture.md#three-path-templates)
are reflected in both sparse features and Neo4j queries.

**Why separate treatment labels?** Treatment links are the answers used to
evaluate retrieval. Letting features or projections traverse those answer
edges would make the task circular. The importer allows only the four evidence
families; the separate label set also supports the known-treatment badge.
See the [import tests](../tests/test_neo4j_integration.py).

## Queries and performance

**Walk through one actual Cypher query.** Start at the compound and disease IDs,
match a permitted typed path, apply the distinct-gene condition, and return a
bounded set of paths. The IDs and limit are parameters. Relationship choices
come from code's allowlist; user or model text never becomes executable Cypher.
Open [PATH_QUERIES](../app/neo4j_repository.py) and explain every clause.

**What do constraints, indexes and UNWIND each do?** Uniqueness protects entity
identity and supports indexed ID lookup. Name indexes are separately declared
for relevant domain lookups. `UNWIND` turns a parameterized batch into rows;
`MERGE` makes repeated ingestion idempotent. The completed dataset marker binds
the database to the prepared graph, preventing an incompatible nonempty volume
from being silently combined with new source data.

**How does query cost grow?** A fixed maximum path length does not make every
query cheap: high-degree genes can create many path combinations. Indexed
anchors, typed patterns and bounded outputs reduce work; a display `LIMIT` is
not a guarantee of universally constant runtime. The
[PROFILE experiment](../reports/query_optimization.json) measures a specific
indexed identity lookup against an equivalent scan. Explain its database-hit
change and machine-specific latency without generalizing it to every query.

**Why two GDS algorithms?** Personalized PageRank provides graph proximity;
target-neighborhood similarity compares compounds through their targets. These
answer different exploratory questions from the supervised treatment-link
ranker. The interface reports whether a result came from actual Neo4j/GDS or a
local algorithm; the notebook's local computation is not called live GDS.

## Ranking, evaluation and explanations

**What was held out?** The recorded reference splits 755 known treatment pairs
into 528 training, 113 validation and 114 test pairs. It is a transductive pair
split: an entity may occur in several splits. It evaluates retrieval of held-out
links among known entities, not generalization to unseen diseases. See the
[saved protocol](../data/processed/evaluation.json) and [model card](model_card.md).

**What are the negative examples?** Disease-matched unobserved pairs, with known
positive pairs excluded from sampling. Absence from this dataset does not prove
ineffectiveness. Evaluation ranks the full compound universe, including zero-path
candidates; training/validation positives for the query disease are masked.
Point to an actual failure as well as aggregate metrics.

**What do the scores and signed terms mean?** A fixed logistic model transforms
the recorded path and degree features using its saved training scaler. The
intercept plus signed contributions reconstructs the logit; applying the sigmoid
reconstructs the score. Terms are relative to the training means, so an absent
feature can still have a nonzero contribution. They are not causal effects or
clinical probabilities. See the [assessment contract](api.md#selected-compound-assessment).

**Why can removing evidence improve a rank?** Rank is relative to competitors,
and feature changes interact with fitted coefficient signs and degree
normalization. A lost record need not reduce every score. Challenge mode keeps
the model fixed so it measures evidence sensitivity without also retraining.
A candidate with no surviving paths has no supported rank; its finite diagnostic
score remains inspectable without being presented as surviving support.

## Agent authority and reliability

**What can the LLM actually choose?** A typed `investigate` or `challenge` plan,
allowlisted exclusions and a result limit from one to ten. LangGraph orchestrates
resolution, retrieval, ranking/assessment and explanation. The LLM cannot write
to the database, supply Cypher, change the score or invent benchmark labels.
Show [ToolPlan and the graph](../app/agent.py), not just a screenshot of a response.

**How are bad requests and bad model outputs different?** A destructive or
ambiguous user request can stop before the provider. Invalid provider output
must also be rejected after the HTTP response is parsed and before scientific
tools run. The [seven-case injected-output test](../tests/test_agent.py) proves
that latter boundary using controlled responses. Label the injection honestly;
the [live HTTP suite](../tests/test_llm_live.py) separately checks actual inference.
On fallback, the actual response mode is explicit; configured `auto` is only a
policy and is not proof that an LLM ran.

## Exact audits and their limits

**What makes the binding audit exact?** Each compound owns its binding records.
With downstream evidence and the model fixed, local deletion envelopes give
the focus's worst score and each rival's attainable score at each allowed cost.
The global calculation shares the deletion budget between the focus and rival
promotions. Exactness depends on those assumptions and the declared finite
budget; see the [proof](binding_audit_proof.md).

**Why is a source group different?** One annotation group can remove records
from many compounds, so compounds' changes are correlated. The provenance audit
enumerates allowed group subsets and reranks all compounds together. Overlaps
remove the union once. A conditional protection set rules out certain
withdrawals; reviewing a source does not prove its records true. See the
[provenance semantics](provenance_audit.md).

**What is new in the joint audit?** Passing each separate test does not establish
survival when both changes occur together. The joint algorithm conditions on
each group scenario, then allocates one additional surviving record deletion
across the whole candidate set. It checks all four budget cells, keeps support
loss separate from supported rank, and does not double-remove overlapping
records. The [reference experiment](mixed_audit_results.md) found 30 pairs that
passed both separate axes but failed jointly; four failures escaped the stronger
of both greedy orders. Those counts have different denominators and meanings.

**What does certificate verification establish?** It binds claims to the graph,
model, arithmetic and scope, recomputes the bound with the same proven algorithm,
and independently replays attaining witnesses using edited matrices. A content
hash alone cannot validate a rank claim. Exhaustive tiny-graph tests separately
check optimizer correctness. A finite-model certificate is not proof of clinical
efficacy, false source data or independent biological evidence.

## Deployment, ownership and open claims

Be able to run `make help`, `make lint`, `make test` and `make docker-run`, and
explain the services, ports and data flow. `make test INTEGRATION=1` adds genuine
Neo4j/Cypher/GDS checks; `make test-llm` requires actual provider inference. Know
which source commit, graph and model produced the notebook, live response and
certificate being shown. A shared random seed does not authorize substituting
one fit's artifacts for another's.

Identify the substantive changes and reviews each teammate personally performed.
No team lead or balanced contribution is assumed from registration. Finally,
separate demonstrated engineering from untested clinical or business claims:
the dataset has licensing restrictions and gaps, and commercial value requires
a prospective evaluation. See [authorship](authorship.md), the
[license inventory](licensing_audit.md) and [pilot protocol](commercial_pilot.md).
