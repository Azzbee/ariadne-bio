# ARIADNE v1.4.0 research evidence

This directory contains executed reference measurements for exact joint
source-group and residual-record withdrawals. It is separate from fresh CI
artifacts: a new CI run has its own source, model and execution identities.

## Complete prepared-Hetionet cohort

The [summary](mixed-audit-summary.json) and
[full query-level report](mixed-audit-benchmark.json) cover all 137 diseases and
1,330 canonical baseline supported top-ten pairs. All 30 pairs that passed both
separate one-group and one-record checks failed the joint check. The exact audit
found all 1,330 declared-scope failures; the stronger outcome of both greedy
orders found 1,326. These are fixed-model sensitivity results, not clinical or
probabilistic claims. A group can withdraw many records.

| Artifact | Meaning |
| --- | --- |
| `mixed-audit-benchmark.json` | Complete population, per-query frontiers, comparator outcomes, work counts, input/source identities and measured runtime |
| `mixed-audit-summary.json` | Derived counts and the full report's SHA-256 |
| `mixed-audit-example-*.json` | Five complete, explicitly selected example certificates; selection rules are in the full report |
| `mixed-audit-greedy-counterexamples.json` | Complete four-case subset missed by both greedy orders, regenerated certificate-hash matches and 17 fresh witness replays |
| `mixed-audit-results.svg` / `.png` | Figures rendered from the retained report |
| `mixed-audit-figure-manifest.json` | Report, renderer and image hashes |
| `mixed-reference-execution.json` | Actual command, start/finish times and exit code zero |
| `mixed-reference-source.json` | Exact clean source checkpoint and deterministic source archive identity |
| `scaling/` | Separate executed synthetic scaling study, including raw timings and all generated input bytes |

The reference used clean checkpoint
`3f14898bdcc85147ec577287daea7240dae9ec30`. Its seven scientific module hashes are
recorded and match the current implementation. The exact checkpoint is retained
as `reference-source-3f14898.tar.gz` in the release verification material and is
also available as the [adjacent source archive](reference-source-3f14898.tar.gz).
This is not a claim that the local checkpoint is a public GitHub commit. The full report
hash is `d07d34e1afd404aaace4fc083ecd9f5c9b872256613378dad338fdc2487f675e`.

## Reproduce

Use the matching source and retained fitted model. Prepare only the pinned graph
with `python -m scripts.prepare_data`; `make data` retrains and may change the
model identity. Then run:

```bash
python -m scripts.benchmark_mixed --data-dir data/processed \
  --output /tmp/ariadne-mixed-reference/mixed-audit-benchmark.json
python -m scripts.verify_audit reports/v1.4.0/mixed-audit-example-interaction.json \
  --data-dir data/processed --output /tmp/ariadne-mixed-verification.json
```

Fresh runs have new timestamps and wall times. Numerical results and certificate
identities are bound to their actual graph, model, group catalogue and declared
arithmetic. See the [method](../../docs/mixed_audit.md),
[proof](../../docs/mixed_audit_proof.md),
[executed results](../../docs/mixed_audit_results.md),
[prior-art comparison](../../docs/research_atlas.md), and
[scaling protocol](../../docs/mixed_scaling.md).
