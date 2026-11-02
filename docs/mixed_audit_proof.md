# Exact ranking certificates for simultaneous group and record withdrawals

## Problem and numerical function

The two earlier audit families answer different questions. A binding audit
withdraws individual BINDS records. A provenance audit withdraws annotation
groups, removing the union of their records. Passing those audits separately
does not certify their simultaneous application.

Fix a disease, a fitted model, the compound universe and the
[`decimal80-binary64-v1` arithmetic contract](audit_numerical_contract.md).
Compound scores, support and score/identifier tie breaking are exactly those
defined in the [binding proof](binding_audit_proof.md). Neither the model nor
downstream biological relations change during an audit.

Let `E` be the recorded binding edges, partitioned into the disjoint outgoing
edge sets `E_i` of compounds `i`. Let `G` be a selected finite catalogue of
annotation groups. Each group `g` has a set of records `Q_g ⊆ E`; groups may
overlap arbitrarily. For selected withdrawals `A ⊆ G`, define

\[
Q(A)=\bigcup_{g\in A} Q_g.
\]

A mixed scenario is a pair `(A,T)` satisfying

\[
|A|\leq b_g,\qquad T\subseteq E\setminus Q(A),\qquad |T|\leq b_e.
\]

The graph loses `Q(A) ∪ T`. A residual record already removed by a group is
not counted a second time. Different action pairs can produce the same edited
graph; counting action pairs is therefore not counting distinct graph worlds.
The public implementation supports `b_g,b_e ∈ {0,1}` and at most 16 selected
groups. The theorem below also describes larger finite bounds **only if** all
required conditional local states are enumerated; the implementation makes no
such larger-budget guarantee.

An annotation group is a conservative quarantine unit, not a verified
independent source, an experiment, or a claim that any record is false. The
[provenance semantics](provenance_audit.md) continue to apply.

## Lemma 1: conditional separability

Fix `A`. Write `E_i^A = E_i \ Q(A)`. These surviving edge sets remain disjoint.
For any residual withdrawal `T`, the surviving path counts and degree of
compound `i` depend only on `T_i = T ∩ E_i^A`. The shared group deletion changes
the starting state of many compounds, but after it has been fixed, residual
deletions again separate by compound.

**Proof.** Every predictive path starts at one compound and traverses one
outgoing binding record. Disease associations, interactions, pathways, disease
degree and model parameters are fixed. A residual deletion from `E_j^A` for
`j ≠ i` cannot affect a path starting at `i`. Disjointness also gives
`|T| = Σ_i |T_i|`. This does not assume that scores decrease with deletions. ∎

## Lemma 2: exact conditional envelopes

For every `A`, compound `i`, and exact residual cost `t ≤ b_e`, enumerate all
`U ⊆ E_i^A` of size `t`. Retain the minimum and maximum supported scores,
attaining witnesses and whether an unsupported state is attainable. Empty
supported sets have no score envelope. These extrema are exact for the finite
declared scorer because every admissible local state is considered.

For a fixed focus cost `t`, using its minimum supported score maximizes the
number of rivals that can be ahead. For each rival, take the smallest residual
cost whose maximum supported envelope puts it ahead under score/identifier
ordering. All free rivals are counted, then the cheapest positive costs are
selected until the remaining budget is exhausted. The witnesses do not conflict
because they use disjoint surviving edge sets. The exchange argument in the
[binding proof](binding_audit_proof.md#lemma-4-exact-global-budget-allocation)
therefore applies without change to this conditional graph. ∎

In the shipped `b_e ≤ 1` implementation, the allocation has a particularly
simple form: spend the one residual deletion on the focus, on one rival, or
spend none. The reported witness still identifies the actual record, including
a rival's record when its deletion promotes that rival.

## Theorem: exact mixed rank envelope

Let `R_A(b_e)` be the exact worst supported rank obtained from the conditional
envelopes for fixed `A`, or absent when no supported focus state exists. Let
`U_A(b_e)` indicate that some allowed residual deletion removes all support.
Then the mixed result is

\[
R(b_g,b_e)=\max_{A\subseteq G,\ |A|\leq b_g} R_A(b_e),
\qquad
U(b_g,b_e)=\bigvee_{A\subseteq G,\ |A|\leq b_g} U_A(b_e).
\]

The focus is robustly in the top `k` precisely when `U` is false, `R` exists,
and `R ≤ k`.

**Proof.** Every permitted mixed scenario has some considered `A` and a
residual deletion covered by Lemma 2, so it cannot exceed the reported
supported-rank bound. Conversely, the maximizing conditional group choice
and its local witnesses form a permitted mixed scenario attaining the bound.
The unsupported disjunction is exhaustive by the same partition of scenarios.
These two properties establish both optimality and attainability. ∎

## Executable specialization

For the shipped `(1,1)` scope, the algorithm needs the empty group choice and
one choice for each selected group. The conditional table is shared across
focus compounds for the same disease and selected catalogue.

```text
for A in {empty group choice} ∪ {each selected singleton group}:
    remove the union Q(A) from the binding relation
    compute each compound's supported score with zero residual deletions
    for each surviving binding record e:
        compute only its owner's score and support after removing e
    retain each owner's supported minimum, maximum and support-loss witness

for each requested budget cell and focus compound:
    for each permitted conditional group choice A:
        consider zero or one residual deletion on the focus
        spend any remaining deletion on the cheapest attainable rival promotion
        retain the largest supported rank and any support-loss witness
    select the worst conditional result with deterministic witness tie breaking
```

The implementation includes all rivals even if they were outside the original
top ten. A rival's score can rise after an edge deletion when the fixed model
contains negative coefficients; the maximum local envelope is therefore as
necessary as the focus's minimum. Replaying a selected witness rebuilds the
complete edited path matrices and ranking, rather than trusting these stored
local summaries.

## Corollaries and interpretation of the frontier

The result includes the four cells `(0,0)`, `(0,1)`, `(1,0)` and `(1,1)`.
The zero-group axis equals the matching individual-record scope; the zero-edge
axis equals the matching group scope. For nested budgets, the set of allowed
scenarios grows, so a robustness verdict cannot change from false to true.
The worst supported rank cannot decrease while supported states remain
available. Support loss is separately monotone and is never encoded as rank
zero, which would reverse its meaning.

There is **no** implication

\[
\operatorname{robust}(1,0)\land\operatorname{robust}(0,1)
\Longrightarrow \operatorname{robust}(1,1).
\]

The premise covers the union of two axes; the conclusion covers additional
joint scenarios. An executable counterexample in
`tests/test_mixed_audit.py` uses ARIADNE's actual feature family: all coefficients
are zero except a coefficient of −1 on `log(1 + binding degree)`, with unit
scales, zero means and zero intercept. The focus `Compound::1` has degree two;
the rival `Compound::0` has degree four. Every binding supports a direct path.
One selected group withdraws one rival edge. Either that group or any single
edge leaves the focus ranked first. Together, the group and another rival edge
reduce the rival to degree two. The scores tie, so the declared identifier tie
rule puts the rival first and the focus second. The focus's own score and support
remain unchanged. The test checks both axes and the joint bound, then replays
the witness through independently edited matrices. The separate tiny-graph
enumeration suite checks global maximality over the same operation family.

This is a constructed mathematical counterexample, not a biomedical measurement.
The full benchmark determines how often these interactions occur for the saved
Hetionet model and data.

A positive measured interaction count is useful evidence for auditing the joint
scope. A zero count would remain a legitimate result and would not invalidate
the theorem. An interaction is not statistical or biological synergy.

## Work accounting

For `m_i(A)=|E_i^A|`, a direct joint-world enumeration considers the following
number of action pairs:

\[
N_{\mathrm{actions}}(b_g,b_e)=
\sum_{A\subseteq G,\ |A|\leq b_g}
\sum_{t=0}^{b_e}{|E\setminus Q(A)|\choose t}.
\]

Conditional envelope construction instead evaluates

\[
N_{\mathrm{local}}(b_g,b_e)=
\sum_{A\subseteq G,\ |A|\leq b_g}
\sum_i\sum_{t=0}^{\min(b_e,m_i(A))}{m_i(A)\choose t}
\]

local compound states. It avoids scoring every other compound anew for every
residual edge world. For one residual deletion, these state counts are of similar
order; the saving is **not** an exponential reduction in the number of deletion
sets. They count different computational units, and their ratio is not a
measured speedup. Allocation, certificate serialization, hashing and independent
witness replay also take time. The benchmark reports the actual work counters
and wall-clock time, including the cost of verification and the comparators.

For the prepared 14-label, 11,571-binding graph, the default `(1,1)` scope has
159,259 action pairs. Overlapping annotations and duplicate edited worlds do
not justify interpreting that count as 159,259 independent sources or outcomes.
The exact input identity and work counters are retained in each execution.

The implementation constructs and caches the complete `(1,1)` conditional table
even when a request asks for a smaller rectangle. Accordingly, the proof's
`search_group_budget`, `search_edge_budget` and `local_states_evaluated` describe
that construction; each result's `covered_action_representations` describes its
own requested cell. Repeated focus queries reuse the immutable disease table.

## Why arbitrary group budgets are a different problem

Consider the generalized decision problem with an unbounded input catalogue and
an input group budget `B`: can at most `B` group withdrawals remove every
supporting path of a focus compound? Even with no residual deletion, one
compound, one disease and only direct predictive paths, this problem is
NP-complete.

**Proof.** Reduce the classical [set-cover decision problem](
https://www.cs.umd.edu/~gasarch/BLOGPAPERS/Karp.pdf) to support loss. Given a
nonempty universe `U`, subsets `S_1, …, S_m` and budget `B`, create one gene
`g_u` for each `u ∈ U`, a compound `c` binding every `g_u`, and a disease `d`
associated with every `g_u`. Include no interaction or pathway edges. Group
`j` annotates exactly the binding records corresponding to `S_j`; discard empty
subsets beforehand because they never help a cover and produce no observed
annotation group. Every
surviving binding supplies one direct supporting path. Thus at most `B`
withdrawn groups remove all support if and only if at most `B` selected subsets
cover `U`. The construction is polynomial in the explicit set-system input.
A proposed group set can be checked by taking its union and testing whether any
supporting path remains, also in polynomial time. ∎

This reduction applies classical set-cover hardness to the declared support
definition. It does not depend on the coefficient signs, score calibration or
tie rule. It also does not apply that asymptotic claim to the shipped fixed
limits. The conditional algorithm enumerates
`Σ_{j=0}^{b_g} binomial(|G|, j)` group choices if generalized; its practical
specialization uses only `|G| + 1` choices. The API's one-group budget and
bounded catalogue are therefore part of the computational guarantee.

## Verification contract

The certificate binds data, graph, model, arithmetic, selected group catalogue,
budgets, conditional-envelope digests, results and attaining witnesses.
Verification has two distinct parts:

1. Recompute the conditional envelopes and joint bound from the bound inputs.
2. Independently remove the union of group and residual records from the sparse
   binding matrix, rebuild path counts and compare each distinct witness state.

The first establishes that the claimed optimum matches the specified algorithm;
the second checks attainability through a different path-count computation.
A checksum alone is insufficient. A witness alone is also insufficient to
establish an upper bound. Tiny-graph tests enumerate all allowed joint graph
worlds as an independent maximality oracle, including overlaps, unsupported
states, competitor promotion, ties and falsely rehashed certificates.

The mathematical contribution is this conditional decomposition for the declared
ranked function and perturbation semantics. Mixed-threat certification, graph
robustness and local/global budget allocation already have substantial prior
art; see [the research position](research_atlas.md). This theorem does not certify
an arbitrary GNN, refitting, new edges, downstream relation deletions, source
independence, error probabilities or treatment efficacy.
