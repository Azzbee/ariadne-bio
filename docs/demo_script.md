# Demonstration script — target 9 minutes 30 seconds

The instructor's 22 October 2026 email limits the video to **ten minutes** and
requires the application interface **and code**. The primary specification also
requires a successful agent request and a guardrail rejecting invalid **LLM
output**. This itinerary covers those requirements before the research extension.

Show the exact source revision and label live interactions, recorded output,
edits and any synthetic narration accurately. A technical video is not evidence
of an individual's contribution or oral understanding. Do not describe an old
run as a new revision's successful execution.

## Timed walkthrough

| Time | Show | Explain |
| --- | --- | --- |
| 0:00–0:30 | Overview, source revision and version status | ARIADNE traces biomedical hypotheses and tests their dependence on graph evidence. Identify the demonstrated commit and whether the interface is live or recorded. |
| 0:30–1:30 | Workbench, schema, disease/candidate and one evidence path | Explain Compound/Gene/Disease/Pathway, stable IDs and all three metapaths. Inspect an actual edge's provenance; treatment labels are separate. |
| 1:30–2:10 | A selected compound's assessment and an evidence exclusion | Show baseline/current rank and signed logit terms. Explain why a rank can improve after removal and why a zero-path diagnostic has no supported rank. Use the actual displayed values. |
| 2:10–3:10 | Joint audit's four-cell frontier and one attaining witness | Contrast one group, one surviving record and both together. Every competitor changes; support loss is distinct from a poor supported rank. Verify the certificate. |
| 3:10–4:10 | Successful live agent request and actual trace | Select Galantamine, then ask about Nicotine. Show named-compound resolution, focused evidence/assessment and ordered candidate context. Require `status: complete` and `mode: llm` before calling this successful live inference. |
| 4:10–4:55 | Invalid provider-output test, then one rejected user request | Run the disclosed seven-case fault-injection test below. Show `plan_validator` rejection and no ranking call. Separately enter destructive Cypher to show the input guard. |
| 4:55–5:40 | Executed notebook and evaluation dashboard | Show graph exploration, saved train/validation/test split, full candidate universe, baselines and an actual failure. Explain that retrieval quality is not clinical efficacy. |
| 5:40–6:20 | Swagger, Neo4j, GDS and PROFILE evidence | Show live backend identity, endpoint contracts and two GDS algorithms. Contrast the measured indexed lookup with the scan; label recorded measurements. |
| 6:20–7:25 | Relevant code and diagrams | Open ingestion constraints/UNWIND, one bounded parameterized path query, the typed LLM plan and joint-audit verification. Explain choices rather than scrolling through files. |
| 7:25–8:40 | Terminal, Docker and revision-matched verification | Show `make help`, `make lint`, `make test`, `make docker-run`, container health, integration/LLM results and public images. Label pre-executed logs and show their revision. |
| 8:40–9:30 | Actual Git/PR evidence and research limits | Identify real contributions and review evidence without inventing teammate work. Explain the bounded joint-audit result, narrow greedy improvement, data-license limits and open clinical/commercial validation. |

## Prepare before recording

Use the [submission guide](submission.md) and [deployment instructions](deployment.md)
to start the full stack and download its dataset/model in advance. Execute the
quality and notebook route against the retained model without a refit:

```bash
make install
make prepare-data
make snapshot
make lint
make test
make notebook
make docker-run
make test INTEGRATION=1
make test-llm
make smoke
```

The snapshot step enables the exported-case frontend tests; the notebook itself
does not require a browser snapshot.

Capture the source identity with `git rev-parse HEAD` and inspect
`git status --short`; do not describe a modified working tree as a clean release.
For the recording, rerun the required commands or show their complete retained
output with a clear execution date and revision. Installation/model downloads
can be omitted with an explicit preparation label; fabricated terminal output
cannot substitute for successful execution.

The host notebook may use the committed reference model while the API container
fits its own model. Record the actual model identity for each. Do not import a
historical rank value into a live example or replay its certificate against a
different fit. `make notebook-refit` deliberately produces new model/report
artifacts; see [reproduction details](reproducibility.md).

## Provider-output rejection to demonstrate

Run the existing adversarial planner test:

```bash
.venv/bin/python -m pytest -q tests/test_agent.py \
  -k invalid_model_outputs_fail_closed_before_scientific_tools
```

Open [the test and injected responses](../tests/test_agent.py) and
[the actual typed planner](../app/agent.py). The seven cases cover an unauthorized
`delete` action, an extra `cypher` field, an excessive limit, non-JSON content,
an empty choices list, null choices and an unexpected response object. The test
substitutes the provider's HTTP response while exercising the real parsing and
plan validation. It asserts `status: rejected`, a `plan_validator` trace and
that the scientific ranking tool was never called.

Say explicitly: **“These are controlled invalid provider outputs, not a claim
that the live model generated them.”** Then distinguish that boundary from
entering `MATCH (n) DETACH DELETE n` in the UI, which is rejected by the request
guard before a provider or graph tool is called. The successful provider request
in the preceding slot demonstrates real inference separately.

## Ready-to-use agent requests

- “Explain Nicotine for Alzheimer's disease.” — explicitly named Nicotine should override a stale Galantamine selection.
- “Investigate asthma without gene interaction evidence.” — the returned exclusions and path counts should reflect `INTERACTS` removal.
- “What changes when pathway evidence is excluded for multiple sclerosis?”
- “MATCH (n) DETACH DELETE n” — the input guard should reject it before provider/scientific work.

A named disease overrides an old disease selection independently of compound
resolution. Ambiguous names require clarification. Show the actual trace and
response mode rather than assuming that a configured provider was used.

## Certificate verification to record

Export a complete joint certificate from the live interface as `joint-audit.json`.
For independent replay against the **same API container's graph and model**:

```bash
docker compose cp joint-audit.json api:/tmp/joint-audit.json
docker compose exec -T api python -m scripts.verify_audit \
  /tmp/joint-audit.json --data-dir /app/data/processed \
  --output /tmp/joint-audit-verification.json
docker compose cp api:/tmp/joint-audit-verification.json ./joint-audit-verification.json
```

Show the actual exit status and verification result. The CLI also handles
binding and provenance certificates. A witness demonstrates attainability;
optimality additionally needs the verified finite bound. The verifier
recomputes that bound with the same proven algorithm and independently replays
the witness with matrix edits. Small-graph exhaustive tests supply a separate
check of the optimizer. The HTTP smoke test alters a claim and recomputes its
content hash; the verifier must still reject it.

For a certificate exported from the recorded edition, use its matching retained
graph/model instead of the live container. [Release replay](releasing.md) explains
the original per-job inputs and proof identities.

## Explain the current result precisely

The sealed [v1.4 joint experiment](mixed_audit_results.md) covers 1,330
candidate–disease pairs across the canonical supported top tens. Thirty pairs
passed both separate one-operation checks, and all thirty failed the combined
scope. The exact solver also found four failures missed by the stronger outcome
of both greedy orders: **4/1,330, or about 0.30% of the cohort**. These are limited
results for one graph, model and declared action space; they do not establish a
new drug treatment or a universal commercial advantage.

The earlier provenance-only benchmark's null greedy-comparison result remains
valid for its own different problem. Do not replace it with the joint result or
mix their budget units. Historical named examples were selected after the
benchmark; call them illustrations and show their exact source/model identity.
One group can withdraw many records, and overlapping annotations do not imply
independent studies. No withdrawal scenario proves that a source is false.

Use the [defense guide](defense_guide.md) to prepare explanations of the schema,
queries, metrics, agent boundaries and audit proof. Each registered teammate
must identify the decisions and corrections they actually made. Finish with
the public repository and the video link required for Moodle; the
[submission guide](submission.md#human-evidence-and-hand-in) records remaining
hand-in obligations.
