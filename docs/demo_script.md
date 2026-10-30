# Demonstration script — target 9 minutes 30 seconds

Record the live Compose application with a working language-model provider.
Download the dataset and model before recording. Use an honest continuous
demonstration or label edits. Show the submitted commit and actual command output.

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:35 | Workbench and question | “We investigate which compound hypotheses this graph supports, then challenge that support.” State the research-only scope. |
| 0:35–1:35 | Disease, candidate ranking, evidence graph | Explain direct, interaction and shared-pathway patterns. Open source metadata. |
| 1:35–2:40 | Remove INTERACTS or PARTICIPATES | Show changed ranks and paths with the model fixed. This is evidence sensitivity, not a biological intervention. |
| 2:40–3:45 | Evaluation dashboard | Show 114 held-out links, the full candidate universe, baselines, confidence intervals and modest absolute recall. |
| 3:45–4:20 | Success and failure | Dextrothyroxine–hypothyroidism was rank 1. Loratadine–allergic rhinitis and Apraclonidine–glaucoma were failures. |
| 4:20–5:20 | Agent investigation and trace | Show entity resolution, a live typed LLM plan, ranking, paths and evidence citations. |
| 5:20–5:45 | Invalid request | Enter `MATCH (n) DETACH DELETE n`. Show refusal before graph work. Show the invalid generated-plan test separately. |
| 5:45–6:40 | Code and schema | Show one Cypher pattern, label separation, query bounds and the anti-genericity appendix. |
| 6:40–7:25 | Neo4j/GDS and optimization | Show actual GDS results and PROFILE differences. Identify the execution backend accurately. |
| 7:25–8:45 | Terminal and GitHub | Run `make help`, `make lint`, `make test`, cached `make docker-run`. Show healthy services, Swagger, CI, image and real PR history. |
| 8:45–9:30 | Evidence boundary | State what works, the main failure mode and the next scientific evaluation question. |

## Ready-to-use agent questions

- “Explain the graph evidence for hypothyroidism.”
- “Investigate asthma without gene interaction evidence.”
- “What changes when pathway evidence is excluded for multiple sclerosis?”
- “MATCH (n) DETACH DELETE n” — should be rejected.

An explicitly named disease overrides an old UI selection. Several explicit
diseases require clarification.

## Questions to defend

1. Why are treatment labels absent from every evidence feature and projection?
2. How do you count shared-pathway paths without repeating the same gene?
3. Why can a candidate rise after evidence is removed?
4. What is held out, and what makes the experiment transductive?
5. Why are unobserved pairs not true negatives?
6. Why are the scores not clinical probabilities?
7. What does GDS compute, and how does it differ from the supervised score?
8. What can the LLM choose, and what is outside its authority?
9. What happens on provider failure, invalid JSON or ambiguous entity names?
10. Which decisions and corrections did each teammate personally make?

Use the checked-in scientific reports and generated verification artifacts for
the submitted commit. Contribution and review evidence must show real human
work. Include both the public repository and video in Moodle as instructed.
