# Release readiness — 2026-10-29

This review starts from snapshot `dfc99b1`. Visibility must remain private until the owner reviews the changes and outstanding decisions. This is a bounded release-preparation review, not a security audit or a scientific validation of the benchmark.

## Fresh local evidence

Linux, Python 3.14.7; no model calls, downloads of models, GPU work, or paid services. Runtime checks use the standard library. Build tools were installed only in a task-local virtual environment from PyPI.

| Check | Result |
|---|---|
| `python3 scripts/run_tests.py` | 29 passed, no failures/errors/skips; 3.505 seconds, peak RSS 29,524 KiB |
| Exhaustive oracle/state-machine test | 9,331 short streams, 649,452 query cases checked against list-position expectations |
| Sample generation with `configs/sample.json` | 1,074 records, 42,013,514 JSONL bytes, six splits |
| CLI validation | Passed record, oracle, span, pairing, split-isolation, source and file-hash checks |
| `scripts/reproduce.py` | Passed regenerated hashes, stored-file hashes, and source fingerprints |
| CLI scoring with copied gold targets | 204/204 exact on test split; wiring check only, not model performance |
| CLI help and first-record preview | Passed |
| `.venv/bin/python -m build --no-isolation` | Source distribution and wheel built successfully |
| Installed wheel, isolated `python -I -m memory_interference --help` | Passed |
| Extracted source distribution test suite | 29 passed; required source resources verified |
| `git diff --check` | Passed |

The new reproduction regression rejects corrupted bytes, missing files, and extra JSONL files. Previously reproduction could pass when the stored corpus had changed because it only compared regenerated output to the manifest.

Fresh reports and the generated corpus are local ignored outputs in `reports/` and `artifacts/`; they are not a recovered historical release. The compact [release evidence](release-evidence.json) records file hashes and test identifiers. Rerun the README commands to obtain complete reports. Historical reports and the documented 20,000-event claim were not recovered or freshly repeated. Tests cover lengths up to 4,096 events.

## Scope and provenance

The available Git history contains one imported snapshot commit and 22 unique tracked file blobs. All tracked source, tests, configuration, schemas, examples, and documentation were inspected. A targeted scan of every reachable historical file blob for private-key headers, GitHub/AWS token formats, credential assignments, local home paths, and email addresses found no matches. The commit author uses a GitHub noreply address. This limited pattern check is not proof that every possible secret or ownership issue is absent. Original local history was not imported and is outside this review.

Generation uses synthetic namespaces and deterministic seeds. The relational oracle does not import generator, renderer, or state-machine selection code. Algorithmic independence does not establish independent authorship, review, or empirical scientific validity. Existing AI-assistance provenance is retained. No license or third-party ownership grant was inferred.

Missing dataset cards, plans, amendment reports, development logs, and release archives remain explicitly marked omitted in `README.source.md`. Their missing links were removed; no replacement historical evidence was invented.

## Publication checklist

- [x] Standalone setup, generation, validation, reproduction, preview, and scoring instructions.
- [x] Honest historical-evidence boundaries and synthetic-data provenance.
- [x] Regression for reproduction of the actual stored corpus.
- [x] Generated output, build artifacts, and environment exclusions.
- [x] Source distribution includes configuration, schemas, examples, scripts, tests, and docs.
- [ ] Owner confirms source rights/third-party provenance and selects a license; no license currently grants reuse.
- [ ] Owner reviews this branch/draft PR and decides whether the private repository should become public.
- [ ] If claiming broad runtime compatibility, verify Python 3.10 through 3.13 and other Unix platforms; this preparation ran only Python 3.14.7 on Linux. Windows reporting tools are unsupported.
- [ ] Before publishing benchmark conclusions, conduct independent methodology review, tokenizer calibration, and real model evaluation. These are not required to describe this as an experimental generator.

No visibility change, history rewrite, default-branch merge, or publication was performed.
