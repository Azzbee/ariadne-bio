# Exact binding audit: measured results

The exact method certifies worst supported ranks and loss-of-support possibilities
under a global budget of individual binding-record deletions. In this benchmark,
a strong margin-aware greedy comparator found **every top-ten failure** that the
exact method found. It nevertheless underestimated **19 worst supported ranks**
at budget two. The measured contribution is exact bounds and checkable
certificates; this run does not demonstrate additional failure discovery over
that stronger comparator.

Evidence: the compact [summary](../reports/v1.2.0/binding-audit-summary.json),
complete [per-query report](../reports/v1.2.0/binding-audit-benchmark.json),
[implementation](../app/binding_audit.py), and [proof](binding_audit_proof.md).
The reference local run completed on 2026-10-31. Its report records the parent
Git revision with `working_tree_dirty=true`, individual source-file hashes,
graph/model identities and runtime versions. That is an identified local
execution, not a claim that the parent revision already contained this change.
Each CI run produces fresh artifacts for its own checkout.

## Protocol

The workload processes **all 137 diseases** in the prepared Hetionet graph and
each disease's first ten supported compounds under the canonical audit baseline,
or all supported compounds when fewer than ten exist. Three diseases have none.
This gives **1,330 compound–disease queries** and **3,990 budget results** for
budgets zero, one and two. Every query considers all **1,552 compounds** as
possible competitors. There is no manually selected disease cohort, training,
parameter search or model refitting in this experiment.

A failure means that some allowed deletion set either removes every supporting
path for the focus compound or puts its supported rank beyond ten. A robust
verdict means that neither outcome is possible within the declared budget.
Unsupported states have no supported rank; their finite model outputs are not
silently ranked. The underlying eight-feature model and scaler remain fixed.

All **1,330 certificates** passed recomputation of the exact bound. Their
witnesses received **3,990 independent full-matrix replay checks**. The simple
and margin-aware greedy comparators received another **3,789** and **3,818**
witness replay checks respectively, with **zero failed checks**. Repeated
witnesses within a query are checked once. Optimality recomputation uses the
same envelope algorithm; independent exhaustive global enumeration is provided
on small test graphs, not on all real-graph deletion combinations.

## Exact results and the scope of the audit

| Maximum deleted BINDS records | Queries | Certified robust | Fragile | Loss of support attainable |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 1,330 | 1,330 | 0 | 0 |
| 1 | 1,330 | 256 | 1,074 | 79 |
| 2 | 1,330 | 104 | 1,226 | 136 |

Loss of support is included in the fragile count; the columns are not additive.
The zero-budget row is expected because the cohort is selected from the baseline
top ten. Of the queries, 1,074 first fail at budget one, another 152 first fail at
budget two, and 104 remain robust through budget two. These are properties of
this frozen ranker and graph, not estimated probabilities that records are wrong
or that compounds succeed or fail as treatments.

The **focus-only** comparator optimizes deletions of the selected compound's
own binding edges while leaving every competitor unchanged. It is exact for its
narrower action scope, but it does not establish a global guarantee.

| Budget | Global worst rank exceeds focus-only worst rank | Largest rank gap | Focus-only top-ten verdict falsely robust for the global scope |
| ---: | ---: | ---: | ---: |
| 1 | 35 | 1 | 1 |
| 2 | 128 | 2 | 0 |

The two kinds of disagreement are different: a rank bound can be underestimated
without changing a top-ten verdict. At budget two, all 1,226 fragile queries are
also fragile under focus-only deletion, despite the 128 rank-bound differences.

### A rival's record can change the selected compound's rank

For **Nifedipine / vascular cancer**, the baseline rank is ten. At budget one,
focus-only deletion has worst supported rank ten and cannot remove all support.
The global witness instead withdraws the **Pimozide–CALM1** binding record
`e_7bee3cb6116bbe4734d5a450`. Pimozide's model score rises from
`0.7393407351618441` to `0.746599461131895`, promoting it from rank eleven to nine.
Nifedipine's own score stays exactly `0.7458716933074748` and its 130 supporting
paths are unchanged, but its rank becomes eleven.

The [scope-example certificate](../reports/v1.2.0/binding-audit-example-scope.json)
contains the actual record metadata and replayable witness. This case was
selected **after the complete benchmark** as the illustration of the observed
scope error, and was added as the seventh recorded research-edition case.
Selection of an illustration did not change the full research cohort. The record
withdrawal is an operation on evidence; it does not simulate Pimozide inhibition
or a biological effect of CALM1.

## Comparison with two global greedy searches

Both greedy comparators inspect every available next binding-edge deletion
globally and retain the best observed prefix through the requested budget. They
prefer loss of support over a supported state and otherwise maximize the focus's
current supported rank. The difference is their tie rule:

- **Simple rank greedy:** break ties by edge ID.
- **Margin-aware rank greedy:** break rank ties by the smallest focus score minus
  the tenth-highest supported rival score, then the focus score, then edge ID.
  The rival threshold is recomputed after every candidate edit; fewer than ten
  supported rivals gives an infinite positive margin.

Each comparator returns attainable witnesses. Neither has a proof that its
sequential choices find the worst rank or can certify absence of a failure.
At budget one, both examine every singleton and match all exact failure verdicts.

| Comparator at budget two | Top-ten failures found / 1,226 | Missed failures | Queries with a suboptimal supported worst-rank result |
| --- | ---: | ---: | ---: |
| Simple rank greedy | 1,215 | 11 | 86 |
| Margin-aware rank greedy | 1,226 | 0 | 19 |
| Exact global envelope method | 1,226 | 0 | 0 |

The last column counts queries where the comparator's retained result is
supported and its rank is below the exact worst supported rank. A comparator
that attains an unsupported state is reported separately rather than assigned a
numerical rank. The exact row is the bound against which the comparisons are
defined; it is not an independent empirical oracle on the full graph.

The stronger tie rule closes all eleven top-ten misses of the simple comparator.
Reporting only the weaker comparator would overstate the observed discovery
advantage. For an illustration of the remaining rank-bound gap, the declared
largest-gap selection rule chooses **Drostanolone / osteoporosis**: baseline
rank nine, exact and margin-aware rank 35 at budget one, and exact rank 1,353
versus margin-aware rank 567 at budget two. Both already detect a top-ten failure.
The [strong-comparator example](../reports/v1.2.0/binding-audit-example-strong-greedy.json)
is an extrema-selected illustration, not a typical effect estimate.

## Computation and numerical identity

There are **11,571 eligible binding edges**. A budget of two covers **66,949,807
global subsets**, including zero and one deletion. The envelope construction
scores **117,147 local states per disease** across all compounds through budget
two, then allocates the shared deletion budget exactly. It does not explicitly
enumerate all 66.9 million global subsets. These state counts do not imply a
measured speedup over a separately timed exhaustive algorithm.

The complete measured audit, both greedy comparisons and replay checks took
**185.32 seconds** after the graph engine was loaded, on the recorded Linux
runtime with Python 3.12.14, NumPy 2.3.5 and SciPy 1.17.0. This is one local run,
not an API latency guarantee or a hardware-normalized performance comparison.
Dataset download, preparation and model fitting are outside that timing.

The audit scorer deliberately fixes its float64 operation order. Against the
unchanged legacy scorer, all **212,624 compound–disease scores** were compared:
126,860 differed in their final bits, the maximum absolute difference was
`9.992007221626409e-16`, and **zero supported ranking positions changed**. The
certificate applies to the named canonical scorer and exact graph/model
identities. It does not assert bit identity between the audit and legacy scorer,
or between separately retrained models on different numerical runtimes.

## Reproduce or falsify the result

```bash
make data
make benchmark-audits
make test
make verify-scores
.venv/bin/python -m scripts.verify_audit \
  reports/v1.2.0/binding-audit-example-scope.json \
  --data-dir data/processed --output scope-verification.json
make notebook
```

`make verify-scores` requires the historical Git revision from a full clone; a
source ZIP alone does not contain it. The benchmark invalidates all six previous
audit reports before loading data and writes explicit running/failed status on
an incomplete execution. A stale successful file therefore cannot represent the
latest attempted run.

The [complete report](../reports/v1.2.0/binding-audit-benchmark.json) retains every
query, disease summary, comparator outcome and witness IDs. Its compact summary
includes the complete-report byte checksum and each selected certificate's byte
and content checksums. Recompute rather than trusting those hashes as signatures.
Any exhaustive small-graph disagreement, failed edited-matrix replay, rehashed
false certificate accepted by verification, or legacy score regression falsifies
an implementation claim and fails the corresponding test or CI gate.

The work does not yet establish external scientific novelty, prospective review
time savings, purchase demand, source-correlated error coverage, or a clinical
benefit. See the [prior-art comparison](research_contribution.md),
[licensing inventory](licensing_audit.md) and [prospective pilot](commercial_pilot.md).
