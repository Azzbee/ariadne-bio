# Research contribution and closest prior art

## The claim this release makes

ARIADNE v1.3 adds an exact, bounded audit of correlated provider/citation-group
withdrawals and a minimum-cardinality conditional protection plan. Every selected
group quarantines all BINDS records mentioning its imported annotation, including
overlaps and simultaneous competitor changes. All permitted group subsets are
enumerated. The protection problem is the ordinary finite hitting-set problem
on the failing scenario family; the implementation does not claim to invent that
optimizer or the concept of provenance. See the
[group-audit proof](provenance_audit_proof.md) and
[annotation semantics](provenance_audit.md).

The preserved v1.2 method implements an exact audit of a fixed compound ranking under a bounded
number of individual BINDS-edge deletions anywhere in the graph. The method uses
compound separability, exact local score envelopes and disjoint budget allocation.
It includes a competitor whose score improves when evidence is removed. A
certificate includes replayable witnesses and is checked by recomputation.

The contribution is the precisely specified combination of individual-record and
correlated-group audits, conditional protection sets, replayable certificates and
reproducible evaluation on the prepared Hetionet workload. The
[individual-record proof](binding_audit_proof.md) states its separate conditions.
This is a research contribution to assess against prior
art, not a claim of being the first certified ranking method, a new biological
discovery, or demonstrated commercial demand.

Existing v1.1 scores, fixed-model assessments and family-exclusion behavior remain
separate. New audits use the explicit
[`decimal80-binary64-v1` numerical contract](audit_numerical_contract.md): fixed
Decimal transforms, exact integer rounding to binary64, and ordered basic
arithmetic. Legacy explorer outputs are not sealed into new certificates.
Historical scorer identities retain their original strict verification; they
are not silently relabeled as portable.

## Scientific prior art

| Work | Established capability | Boundary of ARIADNE's claim |
| --- | --- | --- |
| [Himmelstein et al., Hetionet/Rephetio, eLife 2017](https://elifesciences.org/articles/26726) | Typed-path drug repurposing, learned treatment rankings and a graph exploration interface | ARIADNE reuses this dataset and path-based tradition; neither the application domain nor path explanation is new. |
| [TxGNN, Nature Medicine 2024](https://www.nature.com/articles/s41591-024-03233-x) | Broad drug-repurposing prediction, multi-hop explanations and sparse sufficient subgraphs | ARIADNE does not claim superior predictive generalization or invent graph rationales. |
| [Kelpie, PVLDB 2022](https://www.vldb.org/pvldb/vol15/p3566-rossi.pdf) | Necessary and sufficient explanations for embedding-based link prediction | ARIADNE audits a frozen explicit path ranker; it does not claim to invent evidence-removal explanations. |
| [CF-GNNExplainer, AISTATS 2022](https://proceedings.mlr.press/v151/lucic22a.html) | Counterfactual graph changes that alter GNN predictions | A small counterexample is a familiar explanation objective. Here the certificate also bounds the worst global rank in the declared search space. |
| [CertDR, CIKM 2022](https://doi.org/10.1145/3511808.3557256) | Certified top-k robustness for neural ranking under word substitutions, using randomized smoothing | ARIADNE does not invent certified ranking. Its perturbations are individual graph records and its finite local envelopes are enumerated without smoothing. |
| [RACE, September 2026 preprint](https://arxiv.org/abs/2609.37650) | Exact relation-subset counterfactual search for a frozen heterogeneous GNN, with minimum deletion sets or infeasibility | Exhaustive relation-family search is not claimed as new. ARIADNE's v1.2 action is an individual BINDS edge, and its budget is global across all competing compounds. |
| [CAS, October 2026 preprint](https://arxiv.org/html/2610.14996v1) | Exact top-k selection under scenario uncertainty, decision certificates and adaptive information acquisition | Certified ranking itself is established. ARIADNE uses the separable structure of its nonlinear path score and a global graph-deletion budget. CAS's guarantees do not transfer automatically to this information model. |
| [Counterfactual Fragility Certificates, 2026 preprint](https://arxiv.org/abs/2609.00366) | Recomputable protocol-level evidence-failure trajectories and greedy fragility measures, explicitly distinguished from formal robustness certificates | ARIADNE claims exact bounds only for its small, specified deletion space; it does not claim to invent evidence-failure audit objects. |
| [Mo et al., Cleaning Uncertain Data for Top-k Queries, ICDE 2013](https://www.cs.hku.hk/~ckcheng/papers/icde13-uncertain.pdf) | Budgeted, potentially unsuccessful information gathering to improve uncertain top-k answers | A future evidence-review planner would need to compare against this literature. This release does not implement or claim an optimal human-review policy. |
| [Schreiber and Amsterdamer, Query-Guided Analysis and Mitigation of Data Verification Errors, ICDE 2026](https://arxiv.org/abs/2603.08612) | Worst-case query uncertainty, risky input tuples and selection of external verifications to reduce uncertainty | ARIADNE does not invent query-guided verification or model review errors, costs and uncertain outcomes. Its protection output is an exact conditional hitting set for a declared finite group-withdrawal catalogue. |
| [Meliou et al., Causality and Provenance in Databases, TaPP 2011](https://www.usenix.org/legacy/event/tapp11/tech/final_files/Meliou.pdf) | Database causality, contingency sets and distinctions between endogenous and exogenous facts | Protected groups are explicit scenario exclusions. ARIADNE does not invent provenance, causal attribution or the idea of limiting which facts can change. |
| [Freire et al., The Complexity of Resilience and Responsibility for Self-Join-Free Conjunctive Queries, PVLDB 2015](https://www.vldb.org/pvldb/vol9/p180-freire.pdf) | Resilience and responsibility through tuple deletions that change query answers | Bounded record/group deletion and hitting-set reasoning have established database precedents. ARIADNE applies finite enumeration to its frozen nonlinear ranked-path function. |
| [Tracking the Impact of Fact Deletions on Knowledge Graph Queries, CIKM 2017](https://researchportal.ip-paris.fr/fr/publications/tracking-the-impact-of-fact-deletions-on-knowledge-graph-queries-/) | Tracking effects of deleted knowledge-graph facts through provenance expressions | The source-group audit does not claim to invent provenance-aware graph updates. It specifies imported annotation unions and jointly changing competitor ranks. |
| [Ramusat et al., Semiring Provenance for Graph Queries, TaPP 2018](https://www.usenix.org/conference/tapp2018/presentation/ramusat) | Algebraic provenance for graph query evaluation | ARIADNE's record-to-group map and finite scenario certificates are a concrete application, not a new general provenance algebra. |
| [InfoBAX, ICML 2021](https://proceedings.mlr.press/v139/neiswanger21a.html) and [DiscoBAX, ICML 2023](https://proceedings.mlr.press/v202/lyle23a.html) | Information acquisition for algorithm outputs and effective, diverse genomic interventions | A graph audit is not an experiment-selection breakthrough; real acquisition utility needs outcome data and a separate comparison. |

Preprints above are identified as preprints, not peer-reviewed validation.
These are close conceptual comparisons, not an exhaustive novelty or patent
search. Research on robustness and ranking extends well beyond the selected
references. In particular, a different attack family or proof technique does not
make the broad idea of certified top-k ranking novel.

## What the exact method adds to this application

The previous family-exclusion interaction removes an entire relation family.
That is useful for interpretation but does not answer whether one or two
individual binding records, including a competitor's, could change shortlist
membership. Scoring only damaged versions of the selected compound also misses
competitor promotion caused by normalization and negative fitted coefficients.

V1.2 computes the selected compound's minimum supported local score at each
cost, each competitor's maximum supported local score, and the cheapest disjoint
allocation that puts competitors ahead. It separately checks complete loss of
support. The envelope extrema are enumerated; the cross-compound allocation is
exact because each additional competitor contributes one rank position and local
edge sets are disjoint. No monotone-score assumption or model retraining is used.

The theorem generalizes to a finite enumerable local budget, but the public API
supports only zero, one or two deletions. Evidence from that implementation must
not be used to claim unrestricted budgets, general GNN certification, source-level
correlated errors or biological intervention effects.

### What changes in v1.3

Provider or citation annotations can link many binding records across compounds.
One group withdrawal therefore cannot be assigned independently to one compound's
budget. Version 1.3 deliberately uses a different algorithm and scope: exhaustive
joint scoring of selected group subsets of size at most two. At most 16 groups
can be selected; the default provider catalogue contains all 14 observed BINDS
provider labels. This bounds the scenario space and makes every claim checkable.

The implementation preserves overlap semantics: a record mentioned by two
withdrawn groups is removed once, and a record with several annotations is not
assumed to have independent corroboration. Every affected competitor changes
jointly. The certificate contains the group-map digest, exhaustive scenario-table
digest, worst supported ranks, separate support-loss witnesses and a bounded
summary of the original shortlist.

It also enumerates the smallest additional protected-group sets intersecting
every failing scenario. This is minimum cardinality, with an exact count of all
optimal sets and a bounded preview. The guarantee is conditional on those groups
being unavailable for withdrawal; a review or experiment has not established
their truth. Missing annotations and unselected groups remain outside scope.

The potentially useful contribution is a reproducible workflow joining those
semantics, exact finite certificates and an inspectable protection choice. It is
not evidence of a new generic robustness algorithm, source independence,
optimal experiment design or a published scientific breakthrough. A provider
budget and an individual-edge budget are different perturbation spaces; their
failure counts must not be presented as a like-for-like accuracy comparison.

## Evaluation designed to falsify the implementation

1. Exhaustively enumerate all global deletion subsets on small graphs and compare
   exact worst ranks and support outcomes with the envelope algorithm.
2. Include non-monotone score changes, rival promotion, score/ID ties, unsupported
   pairs, empty local envelopes and budgets split between the focus and rivals.
3. Replay reported witnesses and alter certificate claims to ensure verification
   rejects inconsistent or mismatched evidence.
4. Benchmark all 137 diseases' canonical baseline top ten with all 1,552 compounds
   eligible as competitors. Report global coverage, local states actually scored,
   focus-only gaps and measured runtime separately.
5. Preserve the exhaustive legacy score-regression gate so an audit improvement
   cannot quietly change the earlier application or its retrospective benchmark.

The output of `make benchmark-audits` is the measurement record. A theorem and a
configured CI gate are not evidence of a successful run. Actual source identities,
test results and benchmark output belong with each release's verification.

Version 1.3 adds the separate `make benchmark-provenance` record. Its tests use
independent tiny-graph enumeration for correlated group deletions and brute-force
protection choices, including overlaps, protected groups, unsupported baselines,
non-monotone score changes and a correctly rehashed false claim. The full provider
benchmark covers the same canonical top-ten workload with all competitors. Any
selected PubMed illustration declares its catalogue and post-exploration
selection; it is not a held-out generalization result.

The [complete local benchmark](audit_benchmark.md) covers 1,330 queries across all
137 diseases. At budget two, the stronger margin-aware global greedy comparator
finds all 1,226 top-ten failures, matching exact search on failure discovery; it
underestimates 19 worst supported ranks. The simple edge-ID-tied comparator misses
11 failures, but that difference disappears with the stronger tie rule. The
empirical result therefore supports exact bounds and verifiable certification,
not an observed top-ten discovery advantage over the stronger baseline. One
budget-one case shows why a focus-only guarantee does not cover competitors.

## Product differentiation and commercial evidence

[Causaly](https://www.causaly.com/ai-platform/platform) already advertises traceable
go/no-go assessments, conflicting evidence and repeatable scientific workflows.
[BenchSci EMET](https://www.benchsci.com/help/get-started/what-makes-emet-different)
advertises live scientific database queries, citations, uncertainty and audit
trails. [insitro TherML](https://www.insitro.com/news/introducing-insitros-therml-rapidly-engineering-the-right-therapeutic-for-the-right-target/)
describes closed-loop active learning with experimental infrastructure. These
vendor descriptions establish product overlap, not independent performance
evidence.

ARIADNE's proposed narrow product is a checkable ranking-sensitivity module for
decision due diligence on a customer's licensed graph. It would need explicit
failure semantics, traceability to customer records and measured savings against
the customer's current process. This repository does not demonstrate purchase
intent, revenue, prospective time savings or a clinically useful discovery.
The [pilot protocol](commercial_pilot.md) defines how that hypothesis could fail;
the [licensing inventory](licensing_audit.md) explains why public research access
does not by itself clear these data for a commercial service.
