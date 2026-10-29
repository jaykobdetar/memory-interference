# Memory interference

A model-free synthetic dataset generator for controlled temporal-memory experiments: retrieve a slot value, select a revision, respect a historical cutoff, and resist distracting identities, keys, labels, and stale recollections.

The generator provides three query modes, four interference conditions, recall on/off pairs, deletion/unset diagnostics, and separate length/delay/revision out-of-distribution splits. A forward state machine validates streams; a separately implemented relational oracle produces targets and evidence certificates. This is algorithmic independence, not a claim of independent scientific review.

## Quick start

Use Python 3.10+ on Linux/Unix. Runtime and tests use the standard library; no network, API keys, models, GPU, or installation is needed. The command-line reporting tools use Unix's `resource` module; Windows is not currently supported. Run from this checkout:

```bash
python3 -m memory_interference --help
python3 scripts/run_tests.py
python3 -m memory_interference generate --config configs/sample.json --output artifacts/my-run
python3 -m memory_interference validate --dataset artifacts/my-run --report reports/my-validation.json
python3 scripts/reproduce.py artifacts/my-run --report reports/my-reproduction.json
python3 -m memory_interference preview --dataset artifacts/my-run --split test --index 0
```

Generation refuses nonempty destinations and caps JSONL output at the configured byte budget (49 MB in the sample configuration). Failed/interrupted runs may retain `.partial` files; use a fresh directory to retry. Validation checks stored records and hashes. Reproduction regenerates hashes and compares both saved corpus bytes and source fingerprints; keep the same source tree and compatible Python version when comparing runs.

Optional library installation in an isolated environment:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
```

For the full research workflow, keep the checkout or extracted source distribution: schemas, scripts, configuration, and tests are source resources, not wheel resources. Installed-package and checkout source fingerprints differ; do not switch between them when validating an existing corpus.

## Inputs, labels, and scoring

Each row follows [the v1.1 schema](schemas/record-v1.1.schema.json). **Only `prompt` is model input.** Targets, evidence, certificates, seeds, IDs, and factors are evaluation metadata; including the entire row leaks the answer. Structured `events`/`query` inputs define a separate presentation condition.

Predictions are JSONL rows containing exactly `id` and `prediction`. A prediction is an object with `status`, `value`, `event_id`, and `revision`. Scoring requires complete ID coverage and exact typed provenance, not just the right value:

```bash
python3 -m memory_interference score --dataset-file artifacts/my-run/test.jsonl \
  --predictions predictions.jsonl --report reports/scores.json
```

Edit [configs/sample.json](configs/sample.json) to change seeds, worlds, lengths, delays, or revision counts. Freeze source and configuration before evaluation; changing world counts can change split assignments. See [formal semantics](docs/SEMANTICS.md) and [the structured example](examples/temporal-example.json).

## Status, limitations, and provenance

This is a development generator, not a validated model benchmark. Fixed templates and synthetic opaque symbols do not establish performance on natural language or real memory tasks. Length is measured in events, not tokens. Recall presence and conflicting recall differ; the recall ablation also replaces a final write. Split isolation and oracle checks do not rule out every shortcut. No training or model evaluation was performed for this release preparation.

The initial commit is a source-only preservation snapshot of the AI-assisted project P0250, dated 2026-10-29. Original local Git history was not imported. Generator inputs are synthetic; there are no external datasets or model calls in the generation path. This describes data provenance, not verified ownership of every source contribution.

[README.source.md](README.source.md) preserves historical documentation. Its datasets, dataset card, experiment plan, amendment, reports, and archive are omitted; they are not fresh supporting evidence. Current checks and outstanding publication decisions are recorded in [the release checklist](docs/RELEASE_READINESS.md).

**License pending:** no license grant is included. The owner must confirm rights and choose a license before an open-source release. Repository visibility remains private pending review.
