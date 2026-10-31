# Commercial pilot protocol: ranking sensitivity in decision due diligence

**Status: proposed research and product validation protocol.** No customer has
been contacted by this document, no paid pilot is claimed, and no savings or
revenue result has been measured. The protocol is ready for review with a
prospective partner; it is not a request to send messages or upload partner data.

## The bounded customer problem

A translational research or external-innovation team has a short list of
compound hypotheses and must decide what evidence deserves review before it
commissions further validation. The proposed module asks which individual
binding records can change the team's model-based shortlist within a declared
deletion budget. It returns a global rank bound and concrete records to inspect.

The current implementation does not select an optimal wet-lab experiment, prove
a mechanism, resolve all source uncertainty or decide whether a treatment is
safe. An unstable rank can reveal sensitivity to a recorded binding edge; a
stable rank can still be wrong. If this narrow output does not change the team's
review work, the product hypothesis has failed even when its mathematics is correct.

## Inputs and permissions before a pilot

The partner must identify the data owner and the rights under which the actual
records may be processed, stored and exported. Existing public graph access and
ARIADNE's MIT code license are not that permission. Review the observed source
licenses, third-party contracts, intended commercial use, derived-output terms,
retention period and deployment location. Record the conclusion and responsible
reviewer outside the automated inventory.

Use a contractually permitted private graph, or a replacement dataset whose
permissions cover the pilot. Do not silently carry DrugBank noncommercial
metadata into a commercial deployment. Retain the license inventory and exact
graph/model versions. The inventory flags text and missing metadata; it never
grants legal clearance.

The first pilot can run without an LLM. If a provider is used, obtain agreement
on the specific information transmitted and provider processing terms before
sending private records. The prototype's normal local loopback deployment is
not a claim of completed enterprise security, SSO or regulated-system validation.

## Study design

| Item | Predeclared protocol |
| --- | --- |
| Unit | One real shortlist review for a fixed disease, candidate universe, graph and model |
| Proposed sample | At least 30 distinct review tasks from at least two projects; a feasibility target, not a power calculation |
| Reference | The partner's ordinary review workflow, with identical available records |
| Intervention | The same workflow plus exact global binding-deletion audit and witness links |
| Assignment | Randomize task/workflow assignment; counterbalance reviewers; prevent a reviewer seeing both versions of the same task |
| Adjudication | Independent domain reviewers, blinded to workflow, assess missed decision-changing records and whether conclusions exceed evidence |
| Primary outcome | Active reviewer minutes to an adjudicated review package |
| Secondary outcomes | Missed decision-changing records, unsupported claims, inter-reviewer disagreement, rerun time, setup cost and repeat-use intention |
| Analysis unit | Task/project, not individual graph edges; clustered bootstrap intervals or a prespecified appropriate model |
| Proposed decision rule | Aim for at least 25% lower median reviewer time with no worsening in adjudicated quality; agree the quality margin and sample-size plan before measurement |

Both arms must see the same evidence and receive equivalent training. Log time
spent correcting mappings, interpreting the failure model and processing output.
Count setup/integration time separately and include it in any economic estimate.
A change in a rank alone does not establish that a reviewer found an important
biological error. Preserve cases where witnesses are technically valid but not
useful to the reviewer.

The 30-task target is a small feasibility study. Confidence intervals may be
wide. Do not convert an inconclusive study into a favorable sales claim; use
its variance estimates to design any larger prospective evaluation. Price and
willingness to pay must be discussed with the actual budget owner and tested by
a paid repeat engagement, not inferred from enthusiasm, market valuations or
another company's funding.

## Failure conditions and what follows

The narrow module is not commercially validated if the strongest inexpensive
baseline is as useful, if reviewer overhead erases savings, if its witnesses
rarely change work, if necessary input rights cannot be secured, or if teams
will not pay to repeat the workflow. Document those results even if the exact
certificate remains mathematically correct.

If customers instead need correlated study failures, that is a new failure model.
It needs publication/experiment-level provenance, dependency rules and a new
algorithm or proof. Do not relabel individual-edge results as source robustness.
If they need next-experiment selection, obtain actual assay outcomes, costs and
noise models and compare with established decision-focused acquisition methods.
The present audit does not supply those observations or an optimal review policy.

## Pilot deliverables

- A signed-off input-rights and deployment decision made by the relevant owners.
- A fixed protocol, task roster, model/graph identities and independent allocation.
- Exact audit certificates, witness replays and review logs for every task.
- A comparison report including negative and inconclusive results and uncertainty.
- A budget-owner decision about a paid follow-on, with no invented endorsement.

For prior-art and product overlap, see [research contribution](research_contribution.md).
For data-specific restrictions and missing metadata, see [licensing audit](licensing_audit.md).
