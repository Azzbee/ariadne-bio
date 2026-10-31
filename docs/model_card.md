# Model card: typed-path treatment-link retrieval

## Intended use

ARIADNE ranks compound–disease research hypotheses from a frozen biomedical
knowledge graph and explains their evidence paths. Its evaluation asks whether
held-out recorded treatment links are retrieved near the top of the ranked list.
It is an educational research instrument. Scores are not calibrated probabilities
of effectiveness, safety, clinical approval or success in a trial.

## Data and features

The exact source archive has SHA-256
`a342ab57e9073e6c02bb5e109d1f16917e6f933be4e5c77ebbaebfa26b984c19`.
Evidence comprises BINDS, ASSOCIATES, INTERACTS and PARTICIPATES only.
All treatment labels are separate from the predictive graph.

Features are exact counts of the three typed paths described in
[architecture.md](architecture.md), their log transforms and degree-adjusted
terms. The saved [model artifact](../data/processed/model.json) contains the
ordered feature names, scaler statistics, coefficients, intercept and selected
regularization. Its definitions are authoritative if the implementation evolves.

No language-model output enters training, ranking, validation or test evaluation.
This prevents an LLM's memorized drug indications from masquerading as graph
retrieval performance.

## Exact selected-compound explanation

Version 1.1 exposes an assessment for one compound–disease pair under the selected
evidence exclusions. It returns the all-evidence baseline and current scenario,
the saved model identity, raw path counts, transformed feature values, training
means and scales, coefficients, and each signed contribution.

For feature value $x_j$, training mean $\mu_j$, training scale $s_j$, coefficient
$\beta_j$ and intercept $\beta_0$:

$$
c_j = \beta_j\frac{x_j-\mu_j}{s_j},\qquad
z = \beta_0 + \sum_j c_j,\qquad
\operatorname{score} = \frac{1}{1+e^{-z}}.
$$

This is an exact decomposition of the fitted logistic model, within floating-point
precision. It uses the same eight features as training: three `log1p(path count)`
terms, three `log1p(path count / degree divisor)` terms, and the `log1p` compound
binding and disease association degrees. The degree divisor is
`sqrt(max(compound_binding_degree * disease_association_degree, 1))`. Removing
BINDS or ASSOCIATES also removes the corresponding endpoint degree. No alternate
explainer model is fitted.

The reference point is the **training-feature mean**, not an empty graph. An
absent feature can therefore have a nonzero contribution. Signed terms add in
logit space; their changes sum to the logit change. They do not sum to a change in
clinical probability, and correlated features prevent treating the terms as
independent biological causes. The sigmoid is nonlinear, so score changes are
shown separately.

A pair with zero surviving paths remains inspectable. Its finite model output is
labeled `unsupported_diagnostic`, `supported` is false, and `rank` is null. It is
excluded from the graph-supported explorer ranking; the finite diagnostic score
is not presented as surviving evidence. This does not change the benchmark,
which intentionally evaluates the full compound universe.

The assessment's baseline always uses all evidence. Rank delta is
`baseline rank - current rank`, so a positive value means an improved position.
Score, logit and evidence-count deltas are `current - baseline`. If either state
has no supported rank, rank delta is null. See the
[API contract](api.md#selected-compound-assessment).

## Split and fitting protocol

The 755 recorded positive compound–disease pairs are sorted, shuffled with seed
42 and divided into 528 training, 113 validation and 114 test pairs. This is a
**transductive pair split**: compounds and diseases may occur in more than one
split. It does not establish generalization to unseen diseases or new compounds.

Training samples up to ten disease-matched unobserved pairs per training
positive, without replacement within each disease. All recorded positives are
excluded from that sampling. The resulting 5,280 unobserved training pairs
are absent labels, not proven ineffective compounds.

The scaler is fit on training rows only. Logistic regression searches
`C ∈ {0.01, 0.1, 1, 10}` and selects the value with best validation MRR.
The saved selected model is then evaluated once on the fixed test split.

For each held-out test pair, ranking starts with all 1,552 compounds, including
those without evidence paths. Training and validation positives for that disease
are masked. Other test positives stay in the ranking. Ties are resolved by
namespace-qualified compound ID, making rankings deterministic.

## Reported metrics and measured results

Recall@10 is the fraction of held-out positive links whose compound appears in
the top ten for its disease. MRR is the mean of `1 / rank` over those links.
Results are micro-averaged over 114 links spanning 47 test diseases.

| Method | Recall@10 | MRR | Median rank |
| --- | ---: | ---: | ---: |
| Typed-path logistic | 0.096491 | 0.043898 | 206.0 |
| Direct overlap | 0.052632 | 0.036544 | 325.5 |
| Target degree | 0.008772 | 0.007232 | 534.0 |
| Total path count | 0.008772 | 0.006862 | 427.5 |

The model retrieves more held-out links near the top than these baselines on
this split. Its low absolute recall also makes the limitation visible. The
report includes 95% percentile intervals from 2,000 bootstrap resamples with
diseases as clusters. The model's Recall@10 interval is 0.0465–0.1596 and its MRR
interval is 0.0193–0.0801. These quantify variation across the observed disease
clusters, not uncertainty from new data collection, another train/test split or
clinical outcomes. The overlapping intervals do not establish statistically
significant superiority over direct overlap.

### Actual examples

| Held-out recorded relationship | Rank | Interpretation |
| --- | ---: | --- |
| Dextrothyroxine — hypothyroidism | 1 / 1,550 | Recovered near the top in this historical dataset |
| Loratadine — allergic rhinitis | 207 / 1,541 | Missed the top ten despite a recorded treatment label |
| Apraclonidine — glaucoma | 1,271 / 1,535 | A substantial failure even with many pathway paths |

These rows describe the dataset benchmark, not current medical guidance.
Examples include the first, median and worst held-out ranks so that favorable
selection cannot stand in for the full result.

## Evidence sensitivity

Challenge mode removes a relationship family, recomputes all affected counts and
degrees, and applies the **same saved scaler and coefficients**. No retraining
occurs. For the recorded test split:

| Exclusion | Recall@10 | MRR |
| --- | ---: | ---: |
| No exclusion | 0.096491 | 0.043898 |
| INTERACTS removed | 0.096491 | 0.042205 |
| PARTICIPATES removed | 0.052632 | 0.033275 |

An unchanged aggregate Recall@10 can coexist with changed candidate ranks and
MRR. Removing evidence is a robustness probe on this representation. It is not
a gene knockout, causal treatment effect or simulation of a patient.

## Material limitations

- The graph reflects historical source coverage and curation bias. Highly studied
  genes and compounds have more opportunities to form paths.
- Missing links mean unobserved evidence. Sampled unobserved pairs contain
  potential false negatives.
- A pair split shares entities across train and test. A disease-disjoint or
  temporal evaluation would answer a different, harder generalization question.
- Biological associations may correlate with drug indications even when direct
  treatment edges are removed. Removing direct labels does not prove that all
  historical information leakage or selection bias is absent.
- A short explanatory path is an association, not a demonstrated mechanism.
- The small split and hyperparameter search do not support broad superiority
  claims. These results belong to this checksum, protocol and model artifact.

Reproduce with `make data`. Inspect every split identity and failure in
[evaluation.json](../data/processed/evaluation.json).
