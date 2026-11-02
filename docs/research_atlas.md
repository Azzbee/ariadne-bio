# Research position: certificates for interacting evidence withdrawals

## Contribution being tested

ARIADNE's mixed audit studies a precise failure mode in evidence-based ranking:
a candidate can survive an individual-record audit and a shared-annotation audit
separately without surviving their simultaneous application. It conditions on
the shared group withdrawal, then exploits the remaining compound-local record
structure to compute an exact rank envelope and an attaining witness.

The deliverable is a defined uncertainty model, a conditional-decomposition
proof, a portable finite-arithmetic implementation, independently replayable
certificates, exhaustive small-graph oracles and a complete prepared-Hetionet
benchmark. It is a research result to evaluate, **not** a claim of NeurIPS
acceptance, global novelty, clinical discovery or commercial demand.

The [completed reference experiment](mixed_audit_results.md) covers every
prepared disease and all 1,330 canonical baseline supported top-ten pairs.
It finds 30 failures invisible to the two separate axes and four failures missed
by the strongest combined greedy comparator. The
[executed scaling study](mixed_scaling.md) retains all 24 synthetic graphs and
72 trials, with complete-world correctness comparisons and measured timings.
These observations belong to their declared inputs and scopes.

## Closest primary research

The following sources were checked on 1 November 2026. The comparison describes
their actual scope; a missing exact match in this search is not proof of novelty.

| Prior work | What is already established | ARIADNE's narrower distinction |
| --- | --- | --- |
| [Hojny et al., ICML 2024, Verifying message-passing neural networks via topology-based bounds tightening](https://proceedings.mlr.press/v235/hojny24a.html) | Mixed-integer verification supporting edge additions/deletions, global/local budgets and topology/feature changes. | ARIADNE uses an explicit frozen path ranker, annotation-union withdrawals and surviving local records. It does not invent mixed graph perturbations or exact verification. |
| [Delattre et al., ICML 2026, Certified Robustness under Heterogeneous Perturbations via Hybrid Randomized Smoothing](https://proceedings.mlr.press/v306/delattre26a.html) | Joint discrete/continuous certificates and the insufficiency of separate modalities under interacting perturbations. | The joint-certification motivation is established. Here the operations are correlated graph-record unions plus residual deletions, without smoothing or a probabilistic guarantee. |
| [Schuchardt et al., ICLR 2021, Collective Robustness Certificates](https://www.cs.cit.tum.de/daml/collective-robustness/) | Exploiting interdependence and shared perturbation budgets when certifying multiple graph predictions. | ARIADNE bounds one candidate's global rank while all rivals may change. It does not invent coupling-aware certification or budget sharing. |
| [Osselin et al., UAI 2023, Structure-aware robustness certificates for graph classification](https://proceedings.mlr.press/v216/osselin23a.html) | Anisotropic, structure-dependent graph certificates rather than a uniform edge-flip radius. | Annotation groups are a concrete structured operation, not a new claim that graph edits have unequal meaning. |
| [Bojchevski and Günnemann, NeurIPS 2019, Certifiable Robustness to Graph Perturbations](https://papers.neurips.cc/paper_files/paper/2019/hash/e2f374c3418c50bc30d67d5f7454a5b4-Abstract.html) | Efficient, sometimes exact graph-perturbation certificates for a broader graph-model class. | ARIADNE's tractability comes from a narrower separable ranker and a small selected group catalogue. |
| [Wu et al., CIKM 2022, Certified Robustness to Word Substitution Ranking Attack](https://doi.org/10.1145/3511808.3557256) | Certified top-`k` ranking using randomized smoothing. | Certified ranking itself is established; the finite graph action space and conditional envelope are the application-specific object here. |
| [Li, Saha and Deshpande, VLDB Journal 2011, A unified approach to ranking in probabilistic databases](https://doi.org/10.1007/s00778-011-0220-3) | Ranking with complex tuple correlations, including generating-function methods and probabilistic dependency models. | ARIADNE supplies no probability of record failure and no calibrated ranking confidence. Its bounds are worst-case over a declared finite set. |
| [Mouratidis and Tang, PVLDB 2018, Exact Processing of Uncertain Top-k Queries in Multi-criteria Settings](https://www.vldb.org/pvldb/vol11/p866-mouratidis.pdf) | Exact top-`k` answers under shared weight uncertainty that correlates record scores. | Shared uncertainty and exact rank regions are established; ARIADNE changes recorded graph support under a fixed scorer. |

The previous [research contribution document](research_contribution.md) covers
the biomedical and provenance foundations, including Hetionet, TxGNN, database
resilience and evidence-verification literature. These comparisons concern
different formal problems. They are not direct predictive-accuracy baselines.

## Falsifiable evaluation protocol

The executable protocol is `scripts/benchmark_mixed.py`. Its population is every
prepared graph disease and its canonical baseline supported top ten. There is
no search for favorable diseases, compound exclusion, refitting or treatment
label use during the audit. Every compound remains eligible to outrank a focus.

1. **Correctness:** recompute every certificate and independently replay its
   distinct witnesses. Test global maximality separately using literal joint
   enumeration on small graphs. Reject altered identities, scores, bounds,
   operations and correctly rehashed false claims.
2. **Non-composability:** count candidates robust on both `(1,0)` and `(0,1)`
   axes that fail `(1,1)`. Report the denominator and zero results honestly.
3. **Same-threat comparison:** compare with both source-first and record-first
   greedy orders, using a rank-boundary margin tie rule and an optimized second
   action. Report their strongest combined outcome as well as each order.
4. **Bound quality:** report worst-supported-rank gaps separately from support
   loss and top-ten failure discovery. Finding the same failures does not mean
   recovering the same rank bounds; a rank gap does not establish a new failure.
5. **Computational accounting:** retain the number of conditional slices, local
   states and covered action pairs. Measure total wall-clock time. Distinguish
   those units and avoid inferring a speedup from combinatorial counts.
6. **Preservation and provenance:** retain scientific module/input hashes before
   and after execution, the real Git revision and dirty-state flag, and verify
   that the fixed model and legacy explorer scores are unchanged.

The same-threat comparison is budget matched. Comparing a group to an individual
record is not: a group can remove thousands of records. The two-axis analysis is
a logical coverage question, not an estimate of group-specific biological risk.
For that reason this experiment does not interpret a group effect as stronger
than a record-count-matched random deletion effect. The existing v1.3 controls
answer their own limited descriptive question and are not silently reused as
mixed-audit validation.

The [formal analysis](mixed_audit_proof.md#why-arbitrary-group-budgets-are-a-different-problem)
also makes the computational boundary explicit: with the catalogue and group
budget as inputs, deciding whether withdrawals can remove all support contains
the classical set-cover problem. The reduction uses one compound, one disease
and only direct paths. It explains why the implemented small-budget guarantee
does not imply a general efficient solver for unrestricted group withdrawals.

## What the evidence can and cannot establish

An exhaustive finite result can establish a worst-case rank for the specified
inputs, scorer and operation space. It cannot establish that an annotation group
will fail, that two groups are independent, that a stable compound will treat a
disease, or that this graph represents all biomedical evidence.

The prepared Hetionet graph is one dataset and one fitted path model. Complete
coverage of its audit cohort is stronger than cherry-picked illustrations but
is still not evidence of generalization to other graph models, datasets or
prospective laboratory outcomes. The small allowed budgets and selected group
catalogue are substantive limits, not hidden implementation details.

The theorem is a compositional extension of the existing local-envelope result.
The generic ideas of mixed perturbations and conditioning are established.
A defensible paper should state exactly what the specialized decomposition,
replay contract and measured interactions add, expose equal-performing greedy
results, and invite independent review of that narrow contribution. A prestigious
venue's acceptance cannot be inferred from a functioning artifact or its test
count.
