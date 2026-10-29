# Memory interference dataset generator

A model-free generator for controlled temporal-memory and interference experiments.

## What is preserved

Creates temporal revision/lookup tasks with an independent oracle, validation/scoring utilities and synthetic sample configuration.

This is a private, source-only preservation snapshot of the user-selected local project **P0250**, prepared on 2026-10-29. The user described these projects as arising from AI-assisted work. This note records archival provenance, not a claim about authorship or scientific validity. The original Git history was not imported.

## Setup and dependencies

Python 3.10+; the runtime uses the Python standard library. pyproject.toml is included.

## Entry points

Start by inspecting python3 -m memory_interference --help. configs/sample.json, schemas/, tests/ and scripts/ explain generation and validation.

## Status and limitations

Large generated datasets, historical logs/reports and cross-review snapshots are not included. Reproduction scripts expect separately retained datasets. No regeneration or scientific validation was performed during this backup.

No project code, installation steps or tests were executed during preservation. Existing README/source claims have not been independently revalidated. For the original project documentation, see [README.source.md](README.source.md).

## Backup scope

Only the reviewed text source, tests, selected manifests/configurations and technical documentation are included. Credentials, .env/auth configuration, raw conversations, personal documents, live state, model weights, dependencies, generated datasets and bulky outputs were excluded. Local originals remain in place until separately approved and safe to remove. A successful source backup alone is not proof that all runtime data or experiment evidence has been preserved.
