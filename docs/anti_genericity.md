# Anti-genericity appendix

## Baseline prompt

The following baseline was generated during this implementation by the coding
assistant for a deliberately simple comparison:

> Design a Neo4j schema for a biomedical application that suggests drugs for a
> disease using genes, interactions and biological pathways. Include an LLM that
> explains its suggestions.

## Basic generated schema

```text
Drug(name, description)
Disease(name, description)
Gene(name)
Pathway(name)
Drug -TARGETS-> Gene
Disease -ASSOCIATED_WITH-> Gene
Gene -INTERACTS_WITH-> Gene
Gene -IN_PATHWAY-> Pathway
Drug -TREATS-> Disease
```

This is a plausible starting point. It identifies the main biological concepts,
but leaves crucial choices unstated: what uniquely identifies a node, which
relations are predictions versus labels, what a displayed path means, how
evidence is sourced, and how a ranking can be evaluated fairly.

## ARIADNE's defended changes

| Design decision | Reason and observable consequence |
| --- | --- |
| Namespace-qualified immutable IDs | Names and symbols collide or change. A disease name is a search field, not a database key. Constraints prevent duplicate imported entities. |
| Preserve the dataset's `Compound`, `Gene`, `Disease`, `Pathway` meanings | A compound binding relation refers to the encoded protein in this dataset. Renaming every relation as a generic association loses biological meaning. |
| Four allowlisted evidence families | Different path templates answer different questions. Family-specific exclusions have a defined interpretation and support a controlled sensitivity experiment. |
| Separate treatment labels | Traversing the answer edge would make treatment recovery circular. The graph used for features excludes treatment and palliation relations before any model is fitted. |
| Exact path counts, bounded displayed paths | Showing twelve paths must not turn twelve into the model's evidence count. Display sampling and full feature computation have different jobs. |
| Distinct genes in the shared-pathway template | C–G–P–G–D with the same gene twice repeats direct overlap rather than providing a second gene connected through a pathway. The feature calculation excludes it. |
| Preserve source metadata and licenses | A generated explanation needs traceable records. Missing primary citations stay missing. Multiple source databases do not automatically imply independent experimental replication. |
| Frozen scaler and coefficients during exclusion | Retraining would confound the effect of removing evidence with the effect of fitting a new model. Challenge mode changes evidence while holding scoring parameters fixed. |
| Full candidate universe in the benchmark | Restricting evaluation to compounds already near the disease would hide difficult negatives and inflate retrieval performance. Zero-path candidates remain in the test ranking. |
| Explicitly transductive pair split | Sharing entities across splits is allowed for this question but cannot substantiate unseen-disease generalization. Split identities are saved for inspection. |
| LLM outside the scoring loop | An LLM may know historical indications already. It interprets questions and explains returned graph records, while deterministic code performs ranking and evaluation. |

## Why a graph is essential

The useful object is a typed relationship pattern across several entities. A
compound sharing a disease gene, reaching another gene through an interaction,
or reaching it through a pathway are different explanations. Neo4j makes those
patterns queryable and inspectable. Graph algorithms add proximity and
neighborhood similarity that are meaningful in this representation.

An isolated flat drug table cannot expose which biological edges an explanation
depends on or which paths disappear after a controlled relationship-family
exclusion. ARIADNE's defining interaction is therefore grounded in the graph
structure.

## What we deliberately do not infer

A path does not establish a causal mechanism. A source database does not certify
clinical usefulness. Removing edges does not reproduce a gene knockout. A
logistic score trained on sampled unobserved pairs is not an efficacy probability.
These boundaries determine API fields, UI language and the evaluation protocol.
