# Demonstration script — target 9 minutes 30 seconds

Record the live Compose application with a working language-model provider.
Download the dataset and model before recording. Use an honest continuous
demonstration or label edits. Show the submitted commit and actual command output.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Workbench and question | “We investigate which compound hypotheses this graph supports, then challenge that support.” State the research-only scope. |
| 0:30–1:25 | Disease, candidate ranking, evidence graph | Explain direct, interaction and shared-pathway patterns. Open source metadata. |
| 1:25–2:10 | Pin Nicotine, then remove INTERACTS | Compare baseline/current rank and signed logit contributions. Remove BINDS to show the retained unsupported diagnostic state. |
| 2:10–3:10 | Exact binding audit | Show Nifedipine / vascular cancer at budget one: the focus-only bound is ten, while a rival's record withdrawal permits eleven. Verify the certificate and explain the frozen model. |
| 3:10–4:25 | Correlated provenance and protection | Show Marimastat / rheumatoid arthritis: first under any two individual deletions, but a provider-group withdrawal permits rank 1,096. Inspect overlaps, the minimum protection assumption and its conditional rerun. Export the dossier. |
| 4:25–5:05 | Evaluation dashboard | Show 114 held-out links, the full candidate universe, baselines, modest recall and one actual failure. |
| 5:05–5:50 | Agent investigation and trace | Select Galantamine, then ask about Nicotine. Show explicit-name resolution, focused evidence/assessment, ordered ranking context and the real LLM trace. |
| 5:50–6:05 | Invalid request | Enter `MATCH (n) DETACH DELETE n`. Show refusal before graph work. |
| 6:05–6:50 | Code, schema and proof | Contrast separable single-edge allocation with joint group scenarios. Explain the conditional hitting set and why a witness alone does not establish optimality. |
| 6:50–7:25 | Neo4j/GDS and optimization | Show actual GDS results and PROFILE differences. Identify the execution backend accurately. |
| 7:25–8:45 | Terminal and GitHub | Execute offline certificate verification. Show current lint/test/Compose logs, Swagger, CI, public image identity and actual PR history. Label pre-executed output accurately. |
| 8:45–9:30 | Evidence and commercial boundaries | Explain precise withdrawal semantics, the null greedy-comparator result, current data-license gaps and the unmeasured commercial pilot hypothesis. |

## Ready-to-use agent questions

- “Explain Nicotine for Alzheimer’s disease.” — should override a stale Galantamine selection.
- “Explain the graph evidence for hypothyroidism.”
- “Investigate asthma without gene interaction evidence.”
- “What changes when pathway evidence is excluded for multiple sclerosis?”
- “MATCH (n) DETACH DELETE n” — should be rejected.

An explicitly named disease overrides an old UI selection. Several explicit
diseases require clarification. The same rule applies independently to compounds.

## Certificate verification to record

Export a certificate from the live interface or save the `POST /api/audit`
response as `binding-audit.json`. Against the matching data/model, run:

```bash
.venv/bin/python -m scripts.verify_audit binding-audit.json \
  --data-dir data/processed --output audit-verification.json
```

Show the actual exit status and verification result. The HTTP smoke gate also
changes a rank claim, recomputes its content hash and requires the server to reject
it. This demonstrates that the hash is not treated as proof of the bound.
Use a witness selected from the actual benchmark when demonstrating competitor
promotion; do not invent a rank change for a convenient disease.

The recorded vascular-cancer case was selected **after** the complete benchmark
as an illustration. Select Nifedipine, `top_k=10`, budget one: the focus-only
worst rank is ten, while the global witness changes only a rival's binding record
and reaches rank eleven. Disclose the selection when presenting it; it does not
replace the all-disease results or establish how often this happens elsewhere.

The Marimastat and selected-PMID examples were also chosen after exploration.
The current provider benchmark gives the same minimum protection-set cardinality
as the strongest tested greedy comparator on all 1,330 queries. Show that null
result alongside the exact certificates and alternative optimum counts. A
protection control changes an assumption about eligible withdrawals; it never
claims that a completed review proves the records true. One withdrawn provider
can quarantine many more records than an individual-edge budget allows.

For a second, narrower illustration, select Crizotinib / Paget's disease of bone
and explicitly select imported PMID 22037378. The certificate covers only that
selected citation group and reaches rank 1,015 from eighth. Do not describe it
as a retraction or independent clinical evidence. The accompanying random
controls match global withdrawn-record counts, not lost focal binding degree,
and remain descriptive postselected comparisons.

## Questions to defend

1. Why are treatment labels absent from every evidence feature and projection?
2. How do you count shared-pathway paths without repeating the same gene?
3. Why can a candidate rise after evidence is removed?
4. What is held out, and what makes the experiment transductive?
5. Why are unobserved pairs not true negatives?
6. Why do signed terms add in logit space, and why can an absent feature have a nonzero term?
7. Why are the scores not clinical probabilities?
8. What does GDS compute, and how does it differ from the supervised score?
9. What can the LLM choose, and what is outside its authority?
10. What happens on provider failure, invalid JSON or ambiguous entity names?
11. Which decisions and corrections did each teammate personally make?
12. Why can local envelopes certify a global edge-deletion budget, and when does the proof fail?
13. Why must competitor promotions share the same deletion budget as the focus?
14. What does the canonical audit scorer change, and why are legacy scores preserved?
15. Why do missing and noncommercial license declarations prevent automatic commercial clearance?
16. Why do provider/citation groups break compound-separable budget allocation?
17. Why is a multi-annotation record removed when any selected group is quarantined?
18. What does a protected group assume, and why can an overlapping unprotected group still remove its records?
19. What is minimum cardinality, how many optimal sets exist, and what did the greedy comparison actually show?
20. Why does the Neo4j importer refuse a legacy or changed prepared graph instead of silently merging it?

Use the checked-in scientific reports and generated verification artifacts for
the submitted commit. Contribution and review evidence must show real human
work. Include both the public repository and video in Moodle as instructed.
