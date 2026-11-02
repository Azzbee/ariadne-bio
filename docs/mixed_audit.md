# Mixed evidence audit

## The question

**What happens if a shared evidence group disappears and one additional binding
record is also withdrawn?**

Passing a one-record test and a one-group test separately leaves that joint case
unchecked. The mixed audit answers it directly, with the same fixed model and
all competing compounds included.

| Group budget | Additional record budget | Meaning |
| --- | --- | --- |
| 0 | 0 | Canonical, unmodified baseline |
| 0 | 1 | Any one recorded binding edge, including a rival's |
| 1 | 0 | Any one selected provenance group |
| 1 | 1 | Any one selected group together with any one surviving binding record |

Each budget means **at most** that number. A group withdraws every binding record
mentioning its imported annotation. The additional record must survive that
group withdrawal; a record is never counted twice. Shared annotations are not
assumed to be independent corroboration.

The default catalogue contains all 14 observed BINDS provider labels. An explicit
selection may contain at most 16 groups. A PubMed audit requires an explicit
selection; a PubMed identifier is an annotation group, not necessarily one
experiment. Unselected and missing annotations are outside the group-withdrawal
scope. Every recorded binding edge, including an unannotated edge or one with
unselected annotations, remains eligible for the residual individual deletion.

## Reading the result

Every cell reports the worst **supported** rank, whether all supporting paths
can disappear, and a combined top-`k` robustness verdict. A missing supported
rank means no supported state is available, not a rank of zero. A witness shows
the group and residual record that attain a result, including changes to rivals.

An interaction failure means both single-operation axes retain top-`k`
membership, while some joint scenario does not. This is a statement about a
frozen ranking function, not a finding of biological synergy or evidence that
the data are wrong. The full benchmark retains zero interaction counts if that
is what the data show.

Unlike the v1.3 provenance audit, this initial mixed scope does not expose
protected-group assumptions or a protection-set optimizer. It asks the joint
robustness question directly. The earlier audit endpoints and certificates retain
their original semantics.

## API and replay

```http
POST /api/mixed/audit
Content-Type: application/json

{
  "disease_id": "Disease::DOID:7148",
  "compound_id": "Compound::DB00786",
  "top_k": 10,
  "group_budget": 1,
  "edge_budget": 1,
  "group_kind": "source",
  "group_ids": null
}
```

`POST /api/mixed/audit/verify` accepts the complete certificate in a
`{"certificate": ...}` object. The offline verifier dispatches using the
certificate's declared method:

```bash
python -m scripts.verify_audit mixed-audit.json --data-dir data/processed \
  --output mixed-verification.json
```

Verification recomputes the bound and independently rebuilds matrix witnesses.
It requires the matching graph and model bytes. A content hash is an integrity
check, not a substitute for replay and not a digital signature.

## Reproduce the research workload

```bash
python -m scripts.benchmark_mixed --data-dir data/processed \
  --output reports/v1.4.0/mixed-audit-benchmark.json
```

The command audits every graph disease's canonical supported top ten, with all
compounds eligible as rivals. It produces the full report, a checksummed compact
summary and complete selected example certificates. It records the actual source
revision, relevant module hashes, raw input hashes, environment and runtime.
It checks that scientific source and input bytes stay fixed during execution.
A failed rerun invalidates every earlier success artifact at the selected output
paths rather than leaving a stale green summary behind.

Two same-scope comparators run in both operation orders: greedily choose the
worst immediate group and then optimize the residual record, or greedily choose
the worst immediate record and then optimize the group. Both use the same
model, available groups, residual-record semantics and competitor universe.
The report includes their combined failure discovery and their supported-rank
gaps. Equality with the exact method is reported as equality, not hidden behind
a weaker comparator.

Examples are selected after the complete deterministic workload using stated
rules. They illustrate mechanisms and are not held-out validation cases.
The [proof](mixed_audit_proof.md) and
[research position](research_atlas.md) describe the scope, prior art and
limitations of the claim.

The [completed full-cohort results](mixed_audit_results.md) retain all 1,330
queries: every one of the 30 separate-axis survivors fails the joint scope,
and four failures are missed by the stronger outcome of both greedy orders.
The separate [executed scaling study](mixed_scaling.md) compares the exact
method with literal full-world recomputation using identical generated inputs.
