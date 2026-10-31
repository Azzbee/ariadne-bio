# Demonstration script — target 9 minutes 30 seconds

Record the live Compose application with a working language-model provider.
Download the dataset and model before recording. Use an honest continuous
demonstration or label edits. Show the submitted commit and actual command output.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Workbench and question | “We investigate which compound hypotheses this graph supports, then challenge that support.” State the research-only scope. |
| 0:30–1:30 | Disease, candidate ranking, evidence graph | Explain direct, interaction and shared-pathway patterns. Open source metadata. |
| 1:30–2:25 | Pin Nicotine, then remove INTERACTS | Compare baseline/current rank and signed logit contributions. Remove BINDS to show the retained unsupported diagnostic state. |
| 2:25–3:50 | Exact binding audit | Return to the complete graph. Show budgets zero, one and two, global versus focus-only worst rank, a concrete witness and certificate verification. Explain competitor promotion and that the model is frozen. |
| 3:50–4:40 | Evaluation dashboard | Show 114 held-out links, the full candidate universe, baselines, modest recall and one actual failure. |
| 4:40–5:35 | Agent investigation and trace | Select Galantamine, then ask about Nicotine. Show explicit-name resolution, focused evidence/assessment, ordered ranking context and the real LLM trace. |
| 5:35–5:55 | Invalid request | Enter `MATCH (n) DETACH DELETE n`. Show refusal before graph work. |
| 5:55–6:50 | Code, schema and proof | Show a Cypher pattern and label separation, then the disjoint compound edge sets and exact budget allocation. Distinguish a witness from an optimality check. |
| 6:50–7:30 | Neo4j/GDS and optimization | Show actual GDS results and PROFILE differences. Identify the execution backend accurately. |
| 7:30–8:50 | Terminal and GitHub | Execute offline certificate verification. Show current lint/test/Compose logs, Swagger, CI, public image identity and actual PR history. Label pre-executed output accurately. |
| 8:50–9:30 | Evidence and commercial boundaries | Explain the precise deletion scope, current data-license gaps, and the unmeasured commercial pilot hypothesis. |

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

Use the checked-in scientific reports and generated verification artifacts for
the submitted commit. Contribution and review evidence must show real human
work. Include both the public repository and video in Moodle as instructed.
