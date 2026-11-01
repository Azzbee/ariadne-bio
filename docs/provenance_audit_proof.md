# Exact correlated provenance-group audits and conditional protection

## Claim and limits

Version 1.3 audits a different uncertainty space from the individual-edge
[v1.2 certificate](binding_audit_proof.md). The model, scaler, candidate universe,
disease associations, gene interactions and pathway memberships remain fixed.
Each selected provenance group is either an observed provider-label string in
`edge.sources`, or an imported PubMed identifier in `edge.data.pubmed_ids`, on
recorded BINDS relationships only.

Withdrawing a group removes **every BINDS record mentioning that group**. A
record with several annotations is removed if any selected group mentioning it
is withdrawn. Overlaps are removed once. This is a conservative quarantine
scenario; it does not mean that the record becomes false, that the associated
publication was retracted, or that its remaining annotations fail to support it.
The imported aggregate annotations do not describe independent corroboration
or experiments well enough to claim those alternative semantics.

The default scope contains all observed BINDS provider labels, currently 14.
An explicit selected subset is permitted. PubMed audits require an explicit
selection. Both kinds are capped at 16 selected groups, and the withdrawal
budget is zero, one or two. An exact result for selected PubMed identifiers says
nothing about the other identifiers in the catalog. Provider strings are kept
exactly as imported: related labels are not merged into an invented independent
source or corporate-family taxonomy.

This module adds a precisely specified application and reproducible evaluation.
Exhaustive bounded enumeration and minimum hitting sets are established methods;
the module does not claim to invent either, or to establish worldwide novelty.
See the [prior-art comparison](research_contribution.md).

## Definitions

Let `E` be the unique recorded BINDS edges. Let `G` be the selected set of at
most 16 group identifiers. Each group `g` has a recorded membership set
`M(g) ⊆ E`. A set `P ⊆ G` can be designated *protected*: its members are
assumed unavailable for withdrawal, without changing the graph or ranker.

For requested budget `B ∈ {0,1,2}`, the allowed withdrawal scenarios are

\[
\mathcal{S}_{B,P} = \{S \subseteq G\setminus P : |S|\le B\}.
\]

The removed records and resulting graph in scenario `S` are

\[
R(S) = \bigcup_{g\in S} M(g), \qquad H_S = H\setminus R(S).
\]

The budget counts group identifiers, not records. A single selected provider
can affect thousands of records and many competing compounds. Two different
groups can have equal membership sets, but they remain distinct actions and
distinct protection conditions. Edges with no annotation of the selected kind
cannot be removed by this uncertainty model.

For compound `c`, let `r_c(S)` be its supported rank under the declared scorer,
now `decimal80-binary64-v1`. The [numerical contract](audit_numerical_contract.md)
specifies each Decimal transform and binary64 rounding operation. Both audit
families use the same three path families, eight feature terms, normalization,
fixed coefficient order and score/compound-ID tie rule. Historical certificates
explicitly declaring `float64-fixed-order-v1` retain their original strict
runtime-dependent verification. A compound
with no surviving paths has a finite diagnostic score but no supported rank.

## Lemma 1: exact scenario scoring with overlapping groups

For a fixed disease and fixed downstream graph, let `a_g` be the vector of
direct, interaction and distinct-gene pathway contributions from gene `g`.
These are the same integer contributions already established for the binding
auditor. Each predictive path begins with exactly one compound-binding edge.

For compound `c`, its surviving count vector is therefore

\[
p_c(S) = p_c(\varnothing) -
\sum_{(c,g)\in R(S)} a_g.
\]

Its remaining binding degree is its original degree minus the number of its
distinct binding records in `R(S)`. The explicit union makes overlapping
annotations contribute once to both subtractions. All other feature inputs
remain fixed. Substituting these exact counts and degrees into the declared
scorer gives the same finite function as editing the binding matrix and
rebuilding all three sparse path products. Independent witness replay performs
that second computation.

This lemma does **not** separate the group budget by compound. A group can
change the focus and many competitors simultaneously. Every scenario reranks
the complete compound universe jointly; no independent local extrema are
combined into a fictitious unattainable world.

## Theorem 1: exact worst supported rank and support loss

The implementation enumerates every `S ∈ S_(B,P)`, including the empty set.
Consequently,

\[
W_c(B,P)=\max\{r_c(S):S\in\mathcal{S}_{B,P},\ c\text{ supported in }H_S\}
\]

is an attained exact worst supported rank. If the set is empty, the reported
rank is null. It separately reports whether **any** allowed scenario leaves
the compound unsupported, and retains an attaining witness for each applicable
claim. A compound is robustly supported in the top `k` if and only if no allowed
scenario removes all support and `W_c(B,P) ≤ k`.

No monotonicity of scores or ranks is assumed. A record withdrawal can improve
a score, promote rivals, or move a previously excluded compound into the
shortlist. Complete enumeration also covers such cases. The full set of budgets
is nested, so worst supported rank cannot improve as the budget increases, and
attainable support loss cannot disappear. Those facts concern expanding the
allowed worlds; they do not claim that an individual larger withdrawal has a
worse outcome.

## Theorem 2: exact minimum additional protection

Define the failing scenarios for the selected compound and requested budget:

\[
\mathcal F = \{S\in\mathcal S_{B,P}:
c\text{ is unsupported in }H_S\ \lor\ r_c(S)>k\}.
\]

An additional protected set `Q ⊆ G\P` makes the selected compound robust
exactly when

\[
\forall S\in\mathcal F,\quad S\cap Q\ne\varnothing.
\]

**Proof.** Additional protection permits precisely the old scenarios that do
not intersect `Q`. If `Q` intersects every failing scenario, none remains
permitted, so all remaining worlds satisfy the shortlist condition. Conversely,
if a failing `S` avoids `Q`, that same graph remains allowed and is a
counterexample to the claimed robustness. This reasoning needs no monotone
relationship between record removal and the rank.

The implementation enumerates candidate `Q` in increasing cardinality. The
first cardinality with a feasible hitting set is therefore the global minimum.
It enumerates that entire cardinality layer, counts **all** minimum-cardinality
solutions, and retains a deterministic representative plus at most 12 preview
solutions with explicit truncation. These are minimum-cardinality sets; they
are not merely inclusion-minimal sets. No cost weights are assumed.

Two boundary cases are explicit. If there are no failing scenarios, the empty
protection set is the unique optimum of cardinality zero. If the baseline
already fails, the empty withdrawal scenario belongs to `F`; no protection can
intersect it, so the result is `impossible_baseline`. Protecting every group
otherwise always leaves the successful baseline as the only world.

Protection conditions apply to **group actions**, not record immunity. If a
record mentions both `A` and `B`, protecting `A` does not prevent unprotected
`B` from withdrawing that record. Calling a group protected does not establish
its truth, make a real review infallible, or select a useful wet-lab experiment.
The optimization is conditional on an explicit assumption supplied by the user.

## Search size and implementation bounds

For `n` selected groups, exhaustive construction evaluates

\[
N(n)=1+n+{n\choose2}.
\]

The current 14-provider scope has **106** scenarios; the 16-group cap has
**137**. Scenario tables are cached by disease and the exact selected group-ID
tuple. They always cover construction budget two. Requested budgets and
protected groups filter that table afterward. Accordingly,
`proof.scenarios_evaluated` and `proof.search_budget` describe construction,
whereas `proof.covered_scenarios` and each result's `scenario_count` describe the
actual requested guarantee. Caching does not change the model or scenario scope.

Protection enumeration examines at most `2^n ≤ 65,536` candidate conditions.
At budget two, all nonempty failure sets are singletons or pairs, but the
implementation deliberately checks the complete failure family, including
the baseline boundary case. This cap is a computational contract, not a claim
of scalable unrestricted group optimization. Runtime and full-cohort counts
are measured by `make benchmark-provenance`.

## Certificate and independent checks

The certificate binds dataset, raw graph bytes, model, scorer and the **complete
observed group-membership map**, including unselected groups. Its scope names
the exact selected and already protected groups. Each group carries its member
count, affected-compound count and membership digest. Each witness records its
withdrawn group IDs, complete deduplicated union count and digest, affected
compound count, and at most 12 actual source records as an explicit preview.

The full union can be reconstructed from the matching graph and selected group
IDs. Preview truncation never changes the calculation. Neither the 12 records
nor the displayed shortlist limit is the scientific input. The original top-k
shortlist is evaluated jointly; at most 20 rows are displayed, with truncation
reported, while the selected compound remains separately available in its full
certificate even if absent from those rows.

Digests use the documented v1.2 JSON numerical convention by hashing a wrapper
`{"value": object}` through `certificate_digest`. The complete certificate uses
`certificate_digest` directly, omitting only its seal. These application hashes
are integrity checks, not digital signatures or a claim to standard JCS.

Verification first checks the content seal and exact input identities. It then
recomputes the complete certificate in a separate bounded scenario cache,
including the exact minimum-cardinality result and all optimum counts. Finally,
it independently edits sparse binding matrices and rebuilds path products for
every distinct reported witness. The recomputed optimizer uses the same
enumeration algorithm; independent literal-path, all-world and all-protection
oracles on small generated graphs provide a separate correctness test. A valid
witness alone would establish attainability, not maximality or protection
minimality; all three checks are retained.

## Interpretation of comparisons

A rank robust to two individual-edge withdrawals can be fragile under one
provider-group withdrawal because the latter can remove many records together.
That observation does not contradict the v1.2 guarantee. Conversely, an edge
attack can be absent from the allowed provider worlds, and a larger correlated
withdrawal can alter rivals in a beneficial way. Neither uncertainty model
dominates the other without additional assumptions.

The benchmark compares exact protection with a maximum-uncovered-failure greedy
baseline using the same complete failure family, group-ID tie breaking and a
reverse-ID redundancy-removal pass. A feasible greedy plan is checked by
rerunning the exact audit under its proposed conditions. Any observed gap is a
group-count gap in this conditional problem. It does not measure researcher
time, review reliability, clinical decisions or commercial savings.
