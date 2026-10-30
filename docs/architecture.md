# Architecture and graph schema

## Biological evidence model

```mermaid
flowchart LR
    C["Compound"] -->|BINDS| G1["Gene A"]
    D["Disease"] -->|ASSOCIATES| G2["Gene B"]
    G1 ---|INTERACTS| G2
    G1 -->|PARTICIPATES| P["Pathway"]
    G2 -->|PARTICIPATES| P
```

All biological nodes also carry a shared entity identity. A `Gene` in Hetionet
represents the corresponding gene/protein concept used by its integrated sources.
`Compound–BINDS–Gene` therefore records binding to the protein encoded by that
gene, rather than claiming that small molecules bind DNA in every such record.

| Entity | Identifier policy | Imported count |
| --- | --- | ---: |
| Compound | `Compound::` plus the original DrugBank identifier | 1,552 |
| Gene | `Gene::` plus the original Entrez Gene identifier | 20,945 |
| Disease | `Disease::` plus the original Disease Ontology identifier | 137 |
| Pathway | `Pathway::` plus the original source identifier | 1,822 |

| Evidence relation | Stored endpoints | Imported count |
| --- | --- | ---: |
| BINDS | Compound → Gene | 11,571 |
| ASSOCIATES | Disease → Gene | 12,623 |
| INTERACTS | Gene → Gene, traversed symmetrically | 147,164 |
| PARTICIPATES | Gene → Pathway | 84,372 |

Counts are recorded in the [manifest](../data/processed/manifest.json). Identity
is never based on a human-readable name. Original attributes, source fields and
available licenses survive preprocessing. A displayed edge ID points to the
retained source record. Missing publication-level citations remain missing;
database provenance is not promoted into a claim of a specific clinical study.

The 755 known treatment pairs are a separate label table. Neither `TREATS` nor
`PALLIATES` participates in predictive features, GDS evidence projections or
displayed biological evidence paths. A known-treatment badge is a factual lookup
against that separate table.

## Three path templates

| Template | Meaning | Maximum length |
| --- | --- | ---: |
| C–G–D | Compound and disease share a gene | 2 edges |
| C–G–G–D | Target and disease-associated gene interact | 3 edges |
| C–G–P–G–D | Distinct target and disease-associated genes share a pathway | 4 edges |

Sparse matrix products count these paths exactly. The pathway count explicitly
excludes the case where both gene positions are the same node. No self-loop
interaction contributes an artificial extra step. Display limits bound graph
visualization and query results without clipping model features.

## Runtime responsibilities

| Component | Responsibility |
| --- | --- |
| Nginx | Serve the interface, reverse-proxy API and documentation, bound request sizes |
| FastAPI | Validate inputs and outputs, enforce limits, expose structured errors |
| Neo4j | Store and query typed evidence with constraints and indexes |
| GDS | Project evidence and compute personalized PageRank and target-neighborhood similarity |
| Graph engine | Compute exact typed-path features and apply the saved model |
| LangGraph | Orchestrate entity resolution, retrieval, comparison and explanation |
| LLM provider | Interpret/explain structured evidence within the allowed tool boundary |
| Evaluation script | Fix the split, fit preprocessing/model on permitted data and write measured metrics |

## Data flow and reproducibility

The source URL pins a Git commit. The downloader rejects bytes with a mismatched
SHA-256. Preprocessing filters the four node and relationship families, saves the
graph and manifest, and keeps treatment labels separately. Evaluation stores the
actual split identities, selected hyperparameter, model parameters and scores.

The API reports which backend produced its results. A memory engine is useful
for deterministic unit tests and local exploration. The full Compose configuration
uses Neo4j. The exported browser edition identifies its precomputed snapshot and
does not claim to execute live Neo4j or language-model requests.

## Agent control flow

```mermaid
flowchart TD
    Q["Question"] --> V{"Allowed and unambiguous?"}
    V -->|Unsafe| R["Explain rejection"]
    V -->|Ambiguous| C["Request clarification"]
    V -->|Resolved| T["Read-only graph tools"]
    T --> E["Structured evidence + optional challenge"]
    E --> B["Cited research brief + tool trace"]
```

The LLM cannot alter the database, choose benchmark labels or replace model
scores. Query identifiers and relationship choices pass explicit validation.
Relationships are allowlisted, values parameterized, result sizes bounded and
database execution timed out. An unavailable provider is visible in the response
mode rather than disguised as a successful model invocation.
