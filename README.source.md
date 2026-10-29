# Memory interference — v1.1.0

A reproducible, model-free dataset generator for temporal memory: retrieve a value, select a revision, respect a historical cutoff, and resist distracting entities, keys, labels, and stale recollections. This lane covers temporal state only. It contains no social perspectives, planning tasks, or factual knowledge.

The forward state machine validates streams. A separately implemented relational oracle computes every target and evidence certificate. There are no model calls, teacher outputs, retrieved documents, or external datasets.

## Run

Python 3.10+ and the standard library are sufficient on Unix/Linux; the delivered run used Python 3.14.7. Other runtimes/platforms are untested. Run from this directory. Installation is unnecessary.

```bash
python3 -m memory_interference --help
python3 -m memory_interference generate --config configs/sample.json --output artifacts/my-run
python3 -m memory_interference validate --dataset artifacts/my-run --report reports/my-validation.json
python3 scripts/reproduce.py artifacts/my-run --report reports/my-reproduction.json
python3 scripts/run_tests.py
python3 -m memory_interference preview --dataset artifacts/sample-v1.1.0 --split test --index 55
```

Generation refuses a nonempty destination. It writes one example at a time and enforces the configured byte budget. An interrupted or over-budget run retains `.partial` files and has no success manifest. Use a new empty directory for another run. No network, GPU, worker pool, or additional package is needed.

## Delivered sample

| Split | Worlds | Records | Events/example | Evidence delay | Target revisions |
|---|---:|---:|---:|---|---|
| train | 4 | 408 | 80 | 8, 24 | 1, 3 |
| validation | 2 | 204 | 80 | 8, 24 | 1, 3 |
| test | 2 | 204 | 80 | 8, 24 | 1, 3 |
| ood_length | 1 | 102 | 320 | 8, 24 | 1, 3 |
| ood_delay | 1 | 102 | 80 | 48, 64 | 1, 3 |
| ood_revisions | 1 | 54 | 80 | 8, 24 | 8 |

The sample has **1,074 records**, including 1,008 balanced factorial examples and 66 deletion/unset diagnostics. `artifacts/sample-v1.1.0/manifest.json` records exact hashes, seeds, source hashes, byte counts, and world assignments. JSONL plus the supporting files stay under 50 MB.

This is a development sample, not a statistically powered benchmark. The generator also passed an in-memory 20,000-event check; long streams are supported without distributing a large corpus. Lengths count events, not model tokens. The CLI's full factorial must fit the artifact budget, so very large factorial requests deliberately stop at the byte limit. For a single large episode, call `make_record` directly and retain only what is needed.

## Inputs and labels

Each JSONL row follows [record-v1.1.schema.json](schemas/record-v1.1.schema.json). **Only `prompt` is model input.** `target`, `evidence`, `certificate`, IDs, seeds, and factors are evaluation metadata; never concatenate the whole row into a model prompt. A structured-input experiment may use `events` and `query` instead, but is a separate presentation condition.

```python
import json
with open("artifacts/sample-v1.1.0/train.jsonl") as source:
    for line in source:
        row = json.loads(line)
        model_input = row["prompt"]
        supervised_target = json.dumps(row["target"], sort_keys=True)
```

The output object contains `status`, `value`, `event_id`, and `revision`. Value matching alone is insufficient: repeated values can come from unrelated writes. Half-open character spans identify the selected event and copied value. Deletions point to `[DELETED]`; unset answers have no invented evidence span.

To score predictions, provide one JSONL row per example with exactly `id` and `prediction`, where `prediction` is the parsed output object:

```bash
python3 -m memory_interference score --dataset-file artifacts/sample-v1.1.0/test.jsonl \
  --predictions predictions.jsonl --report reports/scores.json
```

The scorer checks complete ID coverage, rejects duplicate/unknown IDs, and reports joint exact accuracy, value/status accuracy, factor strata, group scores, and all-eight-variants-correct counts. It does not invoke a model.

## Change the experiment

Edit `configs/sample.json`: `seed`, IID world counts, `event_count`, delay levels, revision levels, and the three OOD settings. Configuration validation requires each OOD setting to change only its named structural factor. All streams have three query modes, four interference types, and recall on/off. Core records form a complete factorial; six edge cases are added per world. New seeds create independent namespaces. Freeze the config and generator version before evaluation; changing the number of worlds can change hash-ranked split assignments.

See [formal semantics](docs/SEMANTICS.md), [dataset card](DATASET_CARD.md), [experiment plan](EXPERIMENT_PLAN.md), and [measured validation](reports/VALIDATION.md). [The example](examples/temporal-example.json) and its prompt/answer were generated mechanically. Prior failed checks are retained in `reports/development_checks.jsonl`. The v1.0.0 independent review found two issues, addressed in [the v1.1.0 amendment](AMENDMENT_1_1_0.md). The original release is preserved in `archives/memory-interference-1.0.0.tar.gz`. Focused independent recheck is pending; nothing has been uploaded or published.
