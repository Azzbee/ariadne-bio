# Exact ranking audit under bounded binding-edge deletion

## Statement and scope

For one disease, one compound and budget `B` in `{0,1,2}`, ARIADNE audits every
subset of **at most B distinct BINDS edges anywhere in the prepared graph**.
The question is whether the selected compound remains supported and in the top
`k` under every allowed deletion. The model, scaler, compound universe, disease
associations, gene interactions and pathway memberships remain fixed.

The result covers deletion of recorded binding evidence. It does not describe
inhibition, dose, a biological intervention, an entire source failing, or a
clinical effect. Different edges from the same study are not assumed to fail
together. A correlated-source failure model would require different state and
budget definitions and a new proof.

The theorem below is valid for a general finite budget if every required local
state is enumerated. The shipped implementation caps `B` at two as an explicit
computational bound. It does not extrapolate a two-deletion result to larger
budgets.

## Notation and numerical contract

Let `C` be the fixed set of compound identifiers. For compound `i`, let `E_i` be
its outgoing BINDS edges. These edge sets are disjoint, and their union is `E`.
For a deletion set `S`, write `S_i = S ∩ E_i`.

For the fixed disease, let `p_i(S_i)` be the three surviving typed-path counts,
`d_i(S_i)` the remaining compound binding degree, and `a` the unchanged disease
association degree. The eight features are the existing model features:

\[
v_i(S_i)=\left[
\log(1+p_i),\quad
\log\left(1+\frac{p_i}{\sqrt{\max(d_i a,1)}}\right),\quad
\log(1+d_i),\quad\log(1+a)
\right].
\]

The first two entries denote three-component vectors, giving eight scalar terms.
The graph's binary edge representation and the distinct-gene pathway rule are
unchanged. A state is supported exactly when the sum of the three counts is
positive. Unsupported states have a finite diagnostic model output but **no
supported rank**.

The audit defines its own explicit float64 evaluation order: start with the
saved intercept, add each standardized coefficient term in the fixed
`FEATURE_NAMES` order, then apply SciPy `expit`. No fitted parameter changes.
Ranking uses the resulting score descending, then compound ID ascending for
exact score ties. In particular, sigmoid saturation can create score ties even
when logits differ; rank comparisons use scores, not logits.

This canonical scorer makes the audited function explicit. It does not replace
the legacy vectorized scorer in existing rankings or assessments. The audit
reports its baseline alongside the legacy score and rank and their differences.
The guarantee concerns the canonical audit scorer with the bound input/model
identities; it is not a claim about ideal real arithmetic or every platform's
math library. The legacy exhaustive score-regression gate remains separate.

## Lemma 1: separability

Deleting an edge in `E_i` changes only compound `i`'s three path counts and its
binding degree. Every predictive path begins at exactly one compound and crosses
one of that compound's binding edges. The remaining relations and disease degree
are fixed. Thus compound `i`'s supported status and score depend on `S_i`, and not
on `S_j` for another compound `j`.

Consequently, independently chosen local deletion states can be combined into a
valid global state, and their deletion costs add:

\[
|S|=\sum_{i\in C}|S_i|.
\]

This property is specific to the frozen path-based ranker and this deletion
family. A jointly retrained model, a cross-compound normalization, or deletion of
a shared downstream relation would invalidate this argument.

## Lemma 2: exact local envelopes

For each compound and exact local deletion count `t`, enumerate all subsets
`T ⊆ E_i` of size `t`. Retain the minimum and maximum supported scores and a
witness attaining each, plus whether any unsupported state is attainable. Empty
supported sets have no supported envelope.

These extrema are exact for the enumerated finite function. They require no
monotonicity assumption. Removing binding evidence can increase a model score:
the degree-normalized features change and fitted coefficients need not all be
positive. Therefore a competitor's maximum envelope is as important as the
selected compound's minimum envelope.

## Lemma 3: the worst focus state for a fixed cost

Fix the selected compound `f` and exact focus cost `t`. Among supported local
states at that cost, choose its minimum score `L_f(t)` and retain its witness.
For any fixed state of a competitor `j`, lowering the focus score cannot change
`j` from ahead to behind under the declared score/ID ordering. Therefore this
minimum focus state maximizes the number of competitors that can be placed
ahead within the remaining budget `B − t`.

If any focus state with cost at most `B` is unsupported, that alone disproves
robust top-k membership. This is recorded separately from the worst *supported*
rank; a null unsupported rank is never converted to a favorable numerical rank.

## Lemma 4: exact global budget allocation

For the fixed focus threshold, define `c_j` as the smallest local deletion cost
at which competitor `j` has a supported state ahead of the focus. Compare each
competitor's maximum envelope at costs `0..B−t`; retain the least qualifying
cost and its witness. If none qualifies, let `c_j = ∞`.

All competitors with `c_j = 0` are ahead for free. Each additional competitor
contributes one unit to the focus rank and costs `c_j > 0`. Because the local
edge sets are disjoint, no selected competitor's witness conflicts with another.
The maximum number affordable is obtained by sorting finite positive costs and
taking the longest prefix whose sum does not exceed `B − t`.

**Exchange argument.** If a feasible selection contains a competitor costing
more than an unselected one, exchange them. The number ahead is unchanged and
cost does not increase. Repeating yields a cheapest prefix. No longer prefix is
affordable, so no feasible selection can place more competitors ahead.

The resulting rank is one plus the number ahead. Combining the focus witness
and selected competitor witnesses attains that rank in the actual graph. Thus
the bound is both an upper bound and reachable, rather than a loose independent
interval bound that spends the same budget several times.

## Theorem: exact worst rank and robustness

Take the maximum supported rank from Lemma 4 over every feasible focus cost
`t ≤ B`. Every global deletion set decomposes into one considered focus state
and disjoint competitor states, so none has a worse supported rank. The combined
witness attains the reported maximum. By Lemma 3, using minimum focus envelopes
does not miss a worse rank at that focus cost.

Robust top-k membership holds **if and only if** no allowed focus state is
unsupported and the exact worst supported rank is at most `k`. The result is
reported for every budget `0..B`. The focus-only comparison fixes all competitor
edges; its gap from the global result measures the importance of competitor
promotion under this model, not biological risk.

## Global scenarios versus local work

Let `M = |E|` and `m_i = |E_i|`. The number of covered global deletion states is

\[
N_{global}(B)=\sum_{t=0}^{B}{M\choose t}.
\]

The number of local states scored per disease for envelopes is

\[
N_{local}(B)=\sum_{i\in C}\sum_{t=0}^{\min(B,m_i)}{m_i\choose t}.
\]

The prepared graph has `M = 11,571`. At `B = 2`, there are **66,949,807 global
states**, including the empty state and single deletions, and **117,147 local
states** across all 1,552 compounds. The 66,938,235 two-edge pairs are only one
part of the global total. These are combinatorial counts, not measured speedups.
Envelope construction, allocation, replay and serialization also consume time;
the benchmark reports actual runtime separately.

The implementation constructs all local envelopes through budget two once per
disease, even when the request asks for budget zero or one. Accordingly,
`local_states_evaluated` records this cached construction workload and
`proof.search_budget=2`; `covered_global_states` describes only the requested
global budget. Repeated API calls must not be interpreted as independently
rescoring that many states every time.

## Verification and limits

The certificate binds the graph/model identities, scorer, complete candidate
universe, budget, local-envelope digest, bounds and attaining witnesses. The
verifier recomputes the audit and checks the claims and witnesses. Replaying one
witness alone proves attainability, not optimality; matching a hash alone proves
neither. Small-graph exhaustive enumeration provides a separate oracle for the
global result and includes non-monotone competitor-promotion cases.

The content checksum uses an explicit JSON numerical convention. Before sorted,
compact, ASCII-escaped JSON encoding, finite integral floats become integers
(`0.0` and `-0.0` become `0`); all integers must have absolute value at most
`2^53−1`. Booleans remain booleans. Nonintegral binary64 values are preserved
without decimal rounding, and nonfinite numbers are rejected. The convention
applies recursively to the complete object, omitting only `certificate_sha256`
when sealing. Verification uses the same convention when comparing recomputed
claims. This allows a browser's JSON parse/stringify round trip without accepting
any numerical score tolerance. It is a specified application format, not a claim
of implementing a standard JSON canonicalization scheme or a digital signature.

Optimality verification uses the same proven envelope algorithm in a separate
bounded recomputation cache. It is not an independently implemented global
optimizer. Witness replay independently edits the binding matrix and rebuilds
the path counts. The offline verifier is:

```bash
python -m scripts.verify_audit binding-audit.json --data-dir data/processed \
  --output audit-verification.json
```

It exits zero only for a verified object and one for an invalid certificate. Use
the matching graph and model bytes; a certificate from a different retraining or
numerical runtime is not silently accepted as equivalent.

The full-data benchmark evaluates the canonical baseline top ten for each of
the 137 diseases at budgets zero, one and two, considering **all compounds** as
competitors. This cohort is a retrieval-audit workload, not a clinical validation
cohort. Runtime, prevalence of fragile rankings, witness examples and comparisons
with focus-only auditing are empirical observations. No claim is made that all
valid data errors are edge deletions, that two deletions is a natural scientific
error rate, or that a stable ranking predicts a successful treatment.

The [measured benchmark](audit_benchmark.md) reports the full cohort, both greedy
comparators and the null result for additional top-ten failure discovery over the
stronger comparator. Those observations are separate from the proof above.
