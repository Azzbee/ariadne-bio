# Reproduce the notebook without mixing model fits

The saved model, held-out evaluation and complete audit reports belong together.
A fixed random seed specifies the experiment, but numerical libraries and fitting
runtimes can produce different parameter bytes. ARIADNE records the actual model
SHA-256 and rejects reports from a different fit.

## Recommended: inspect the saved reference

Start from a fresh checkout of the version you are assessing, then run:

```bash
make install
make prepare-data
make notebook
```

`prepare-data` downloads the pinned Hetionet archive when absent, checks its
SHA-256 and rebuilds `graph.json` and `manifest.json`. It leaves the committed
model, evaluation and audit reports unchanged. `notebook` uses those matching
artifacts and executes all cells into `demo.executed.ipynb`; it does not refit.
The source `demo.ipynb` retains its recorded outputs until an actual successful
execution is deliberately copied back.

The runner checks graph availability, the shared dataset identity, the exact
model/evaluation identity, and both audit summaries before starting a kernel.
Notebook cells additionally verify graph/model checksums, complete benchmark
coverage, report checksums and the relevant scientific source-file hashes. These
checks do not convert a mismatched report into valid evidence.

This path needs Python 3.11 or later and the pinned development dependencies. It
does not require Docker, Neo4j or a language-model provider. The notebook labels
its local graph algorithms explicitly; live Neo4j/GDS and LLM behavior have
separate integration tests.

## Explicit alternative: fit a new model and refresh its evidence

Use a disposable checkout when you want a new experiment while preserving the
committed reference artifacts in your main working directory. After
`make install`, run:

```bash
make notebook-refit
```

The target runs these stages in order, including with parallel Make:

1. `make data`: prepare the graph, fit the model and write its held-out evaluation.
2. `make benchmark-audits benchmark-provenance`: recompute the two complete
   benchmark reports displayed by the notebook for that fitted model.
3. `make notebook`: validate identities and execute every cell.

The target stops when a stage fails. It replaces the current checkout's generated
model, evaluation and binding/provenance reports. This is an explicit new run;
it does not promise the saved reference's model hash or reuse its benchmark
results. A complete binding/provenance refresh takes substantially longer than
the reference notebook route.

The notebook computes and verifies its illustrative joint-audit certificate
directly. It does not read the separate full v1.4 joint benchmark or synthetic
scaling study. To regenerate those research experiments too, use
`make benchmark-mixed benchmark-mixed-scaling` and retain their recorded inputs
and execution provenance; see [joint results](mixed_audit_results.md) and
[paired scaling methods](mixed_scaling.md).

## Recover from an identity mismatch

If you already ran `make data` or `make evaluate`, the model and evaluation have
been refitted. To keep that fit, refresh the notebook's audit reports without
fitting again:

```bash
make benchmark-audits benchmark-provenance
make notebook
```

To inspect the original reference instead, use a fresh checkout of the same
release and follow the reference commands above. Do not copy an old model over a
new evaluation or edit an artifact's hash to make a mismatch disappear.

## Test the application and actual database separately

`make test` runs the unit, API and frontend suites and enforces the coverage
threshold. With a running, ingested Neo4j/GDS stack and credentials in `.env` or
the environment, use the same required command to include the real database:

```bash
make docker-core
make test INTEGRATION=1
```

The integration mode also runs the live connectivity, Cypher, import and GDS
checks. A missing password or unavailable database is a failure in this explicit
mode. `make test-integration` runs only those checks with the same strict policy.
The real language-model tests use `make docker-run` and `make test-llm`.
