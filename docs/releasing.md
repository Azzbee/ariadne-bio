# Release verification

Release evidence must describe the exact tested source revision. A public image,
a local successful test or a previous release report does not establish that a
new revision passed. All three verification jobs start with their own fresh
checkout identity and remove only their prior generated outputs before installing
dependencies or running tests.
Quality, full-stack integration and the joint-audit research workload run
concurrently on isolated runners. Each retains its own artifacts and fitted
model. Image publication requires all three jobs to succeed for the same
workflow run and source revision.

## Before merging

Use a focused feature branch and an ordinary pull request. Explain the user-visible
problem, implemented behavior, actual validation and any remaining limitation.
Review comments and human contribution claims must describe work that happened;
automated agents do not stand in for a second human teammate.

Run `make data`, `make audit-licenses`, `make benchmark-audits`,
`make benchmark-provenance`, `make benchmark-mixed`, `make benchmark-mixed-scaling`,
`make provenance-controls`, `make snapshot`, `make verify-scores`, `make lint`,
`make test` and `make notebook`.
The PR's fresh runner then executes the complete `make docker-run` path, the HTTP
smoke check, real Neo4j/GDS checks and actual LLM HTTP checks. Preserve failures;
do not convert them to successful fallbacks or skip the provider gate.

When an existing connector cannot write, use an already authorized ordinary
GitHub UI upload or edit on the feature branch, then verify that its complete
source tree matches the tested local tree. Normal UI commits, a PR and an
authorized merge generate the usual CI events. Do not introduce a temporary
contents-write import workflow, invent a token or change account permissions to
work around a rejected publication path. If an approval block remains, state
the blocked action and use a permitted alternative or obtain explicit approval.

## Evidence from the new run

| Artifact | Required content |
| --- | --- |
| `ci-quality.json`, `ci-integration.json`, `ci-mixed.json` | Checkout SHA, Actions run and attempt, job and start time; each job has a separate context |
| `ollama-model.json` | Actual full model digest, expected digest, size and whether it was reused; the reference default must be `verified` |
| `http_smoke.json` | Live HTTP checks, frontend headers, exact assessment reconstruction, retained unsupported pair, complete binding/provenance/joint certificates, recomputed verification and rejection of correctly rehashed false claims |
| `live-model.json`, `live-manifest.json`, `live-evaluation.json`, `live-artifacts-verification.json` | Bytes copied directly from the running API container after smoke, model self-hash and exact identity binding for binding/provider/conditional/PubMed/joint certificates; never substitute another job's fit |
| `v1.2.0/binding-audit-benchmark.json` | Full disease/top-ten workload, graph/model/scorer identities, exact budget results, local/global state counts, focus-only comparisons and actual runtime |
| `v1.2.0/license-inventory.json` | Actual observed license/source counts and missing metadata, bound to graph bytes; legal clearance remains unassessed |
| `v1.3.0/provenance-audit-benchmark.json` and companion reports | Full provider-group workload, exact scenario/protection outcomes, selected PubMed scope, source/model/group identities, runtime and actual verification |
| `v1.3.0/provenance-size-matched-controls.json` | Fixed-seed random withdrawals matched on removed-edge count for two disclosed postselected illustrations; descriptive results, not a population or causal claim |
| `v1.4.0/mixed-audit-benchmark.json` and companion reports | Complete four-cell joint workload, independent witness replay, both greedy orders, interaction failures, exact source/input identities, actual runtime and explicit unavailable examples when a selection criterion has no match |
| `v1.4.0/scaling/` | Complete synthetic timing report and summary, matched raw trials, first-trial certificates and every generated graph/model/manifest/evaluation input; preserve the directory recursively |
| `neo4j-junit.xml` | Genuine database and graph-algorithm tests |
| `llm-junit.xml` and `llm-*.json` | Actual planner success, evidence challenge, rejection, and named-compound assessment with correct ranking context |
| Container logs/status and runner resource reports | Startup, service health and disk/memory observations |
| Quality artifacts | Current unit/API/frontend results, coverage, notebook and scientific output identities |

The uploaded evidence is an output of the run. Files preserved in the repository
as historical reference must never substitute for a missing new result. Confirm
the workflow and job conclusions, not just artifact existence.

The [synthetic scaling protocol](mixed_scaling.md) has a separate meaning from
the full Hetionet audit: it compares matched implementations on generated small
graphs. Report actual paired times and the scope of those measurements; counts
of covered actions are not runtime measurements. Before collecting new scaling
evidence, clear its declared generated output directory so an interrupted run
cannot upload an old summary. Retain the entire subtree, including inputs; a
top-level JSON-only artifact glob is insufficient.

Keep four model origins separate: the committed frozen research-snapshot model,
the quality job's fresh fit, the joint-research job's fresh fit, and the running
Compose API's fresh fit. Numerical libraries or execution conditions can produce
small fitted-parameter differences,
so matching seeds and retrieval ranks do not establish matching model identities.
Immediately after successful live HTTP smoke, CI uses `docker compose cp` to
retain the actual container's model, manifest and evaluation. The
`infra.verify_live_artifacts` gate independently recomputes that model's content
self-hash and requires every retained smoke certificate and selected-compound
assessment to identify it and the same prepared graph. All five successful
binding/provider/conditional/PubMed/joint certificates must match.

### Reproduce certificates on another machine

Download `quality-evidence`, `integration-evidence` and `mixed-evidence` from
the actual run, verify the GitHub-provided ZIP
digests, and extract each into a separate directory. Prepare the pinned graph
with `python -m scripts.prepare_data`; this does not fit a replacement model.
Then use the retained parameters directly:

```bash
.venv/bin/python -m infra.replay_ci_certificates \
  --kind quality --artifact-dir /tmp/ariadne-quality-evidence \
  --graph data/processed/graph.json --output /tmp/ariadne-quality-replay.json

.venv/bin/python -m infra.replay_ci_certificates \
  --kind integration --artifact-dir /tmp/ariadne-integration-evidence \
  --graph data/processed/graph.json --output /tmp/ariadne-integration-replay.json

.venv/bin/python -m infra.replay_ci_certificates \
  --kind mixed --artifact-dir /tmp/ariadne-mixed-evidence \
  --graph data/processed/graph.json --output /tmp/ariadne-mixed-replay.json
```

The command requires all six quality examples, all five live certificates, or
both fixed first/last joint-workload examples, according to the selected kind.
Joint replay rederives the first and last canonical top-ten query identities
and the complete observed source-group scope. A valid certificate for a selected
subset or another `top_k` cannot fill one of those benchmark roles.
It checks actual graph bytes, the retained model's parameter self-hash and
evaluation identity, then recomputes every certificate and independently
replays its matrix witnesses. It ignores saved verification verdicts. The
artifact and prepared data remain untouched; a temporary directory receives
the exact retained bytes and is removed afterward. A mismatch returns a
nonzero exit code and replaces any old output verdict with the new failure.
The output must be outside both the extracted artifact and prepared graph
directories, and cannot alias a replay input. Report writes replace the output
atomically, preserving any unrelated artifact file that shares its old inode.

New certificates use the explicitly defined `decimal80-binary64-v1` arithmetic
contract. The historical `float64-fixed-order-v1` implementation is preserved
for old certificates, including its platform-dependent transcendental
functions. Retaining compatibility does not retroactively make old seals
portable. The numerical regression suite retains the actual vector that
exposed an AVX512-dependent logarithm difference, independent static golden
values, and a subprocess comparison across NumPy CPU-dispatch settings.

Before merging a scorer change, replay certificates generated by the fresh CI
runner on a second runtime with the same retained model and graph. Do not
round away or tolerate a mismatch. The replay report establishes numerical
recomputation; artifact origin and actual workflow success still require the
separate download, GitHub job and source-tree checks described above. Raw-byte
hashes and semantic model identity are distinct and both retained.

## Publish and independently verify

After an authorized merge, main CI reruns the gates and publishes API and frontend
images with both `latest` and the full source-commit tag. Verify both packages
anonymously using the OCI registry API or a logged-out container client. Inspect
both tags, compare their manifest digests, check source/revision labels, and verify
all downloaded configuration and layer bytes against their SHA-256 descriptors.
This verifies anonymous image retrieval; container execution is established by
the separate fresh Compose job.

Build a standalone research ZIP from an explicit runtime-file whitelist and the
newly generated snapshot. Include the MIT license, source-data licensing notes,
a local-server README, source revision, and checksums. Extract it and exercise all
seven cases and sixteen exclusion configurations, including compound focus and
unsupported states. Do not package credentials, Git metadata or dependencies.
The v1.2 runtime whitelist must include `audit.js`, `audit-model.js`,
`audit.css` and `integrity.js` along with the prior frontend assets. Exercise recorded audits for
all exported top-k/budget variants and confirm that static verification is
identified as a recorded export-time result, not a live graph recomputation.

Version 1.3 additionally requires `provenance.js`, `provenance-model.js` and
`provenance.css`. Its frozen group-audit presets cover the exported compounds at
top ten with budgets one and two. Explicit citation-group selection and custom
protected-group assumptions require the live API unless the exact requested
certificate was exported; the static client must not invent an uncomputed result.
Verify the complete certificate download and printable dossier, including
truncated witness previews, the exact group catalogue and protection assumptions.

Version 1.4 also requires `landing.js`, `landing-model.js`, `landing.css`,
`mixed.js`, `mixed-model.js` and `mixed.css`, plus the complete local font asset
directory and its licenses. The joint snapshot preset is top ten with group
budget one and residual-record budget one. Every displayed compound must retain
all four frontier cells, the source-group catalogue, matching scientific
identities, and verification tied to the exact certificate. Missing presets
must be unavailable, never synthesized from separate-axis results.

Exercise a fresh landing-page visit without loading a case, the recorded example,
workbench entry, existing case/audit deep links, back/forward navigation, motion
pause, keyboard interaction and narrow layouts. Keep actual screenshots and
browser findings. The hero is a conceptual illustration; its motion is not a
live evidence computation. The recorded example retains its v1.3 identity rather
than being relabeled as a new experiment.

## Versioned packaging command

`infra/package_release.py` is the reproducible packaging entry point. It reads
every source file from an explicit immutable Git revision, never from a dirty
working-tree file. It checks that the separately generated snapshot has the same
application version, prepared graph identity and fitted model identity as that
revision; every snapshot case must match its manifest bytes and SHA-256. It
rejects extra data files, symlinks, path traversal and common secret locations.
Its source archive preserves Git executable modes. ZIP members use fixed times,
sorted paths and fixed compression settings, giving repeatable bytes in the same
Python/zlib runtime. Every ZIP is checked by CRC and full member-byte comparison.

The committed notebook must retain an execution count for every nonempty code
cell and no error output. Run `make notebook`, inspect the actual results, and
save the executed notebook as `demo.ipynb` before committing. The packager can
check recorded notebook structure; actual execution is established by the
separate new CI run, not by the presence of execution counts alone.

After the final source commit and matching snapshot are ready:

```bash
make package-release REF=FULL_TESTED_COMMIT_SHA OUTPUT=dist/release-v1.4.0
```

This writes the source ZIP, standalone research ZIP, recorded executed notebook,
release manifest and `SHA256SUMS`. The output directory must be absent or empty;
earlier deliverables are never replaced. Rebuild into another empty directory
and compare the complete asset hashes when testing reproducibility.

To include a curated verification directory, give it a `SHA256SUMS` covering
every payload and use:

```bash
.venv/bin/python infra/package_release.py \
  --ref FULL_TESTED_COMMIT_SHA --snapshot frontend/data \
  --evidence-dir reports/release-evidence \
  --output dist/release-v1.4.0
```

The additional verification ZIP retains the supplied checksums as
`INPUT-SHA256SUMS`, adds exact source/snapshot provenance and contains fresh
checksums covering every packaged evidence file. Curate only public verification
records; do not pass raw account sessions, credentials or private customer data.
This mechanism packages evidence without authenticating it or inferring that CI
passed. Independently check the actual GitHub run, job conclusions, checkout/tree
identities, reports and registry objects before making a release claim. The
manifest explicitly states this boundary.
The client checks case-file byte counts and SHA-256 values against the served
manifest before parsing/caching. It also binds audit graph/model/dataset identities
to the manifest. These checks detect mixed or corrupted assets; they are not a
signature by an independent authority and do not prove optimality in the browser.

Tag the tested commit, attach the new evidence, and publish checksums covering
all release assets. Keep earlier releases intact. A previous video or snapshot
may remain useful when clearly versioned; do not relabel it as a recording of
features it does not show. Link the release and the live-source instructions in
the README. Complete classroom submission and personal-defense requirements
according to the instructor's actual instructions.
