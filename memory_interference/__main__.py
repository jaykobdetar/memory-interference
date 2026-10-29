"""CLI: python3 -m memory_interference {generate,validate,preview}."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import resource
import sys
import time

from . import __version__, SCHEMA_VERSION
from .generator import canonical, records, DEFAULT_CONFIG, worlds
from .validation import summarize
from .scoring import score


def save_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def source_hashes():
    root = Path(__file__).resolve().parent.parent
    paths = sorted((root / "memory_interference").glob("*.py"))
    paths += sorted((root / "schemas").glob("*.json"))
    paths += sorted((root / "tests").glob("*.py"))
    paths += sorted((root / "scripts").glob("*.py"))
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def generate(config, output):
    # Refuse to replace an existing dataset or silently mix generation runs.
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be absent or empty")
    output.mkdir(parents=True, exist_ok=True)
    counts = {}; hashes = {}; sizes = {}; handles = {}
    byte_count = 0
    try:
        for record in records(config):
            split = record["split"]
            if split not in handles:
                handles[split] = (output / (split + ".jsonl.partial")).open("wb")
                hashes[split] = hashlib.sha256(); counts[split] = 0; sizes[split] = 0
            line = (canonical(record) + "\n").encode("utf-8")
            if byte_count + len(line) > config["max_artifact_bytes"]:
                raise ValueError("artifact byte budget exceeded; .partial files retained for inspection")
            handles[split].write(line); hashes[split].update(line)
            counts[split] += 1; sizes[split] += len(line); byte_count += len(line)
    finally:
        for handle in handles.values():
            handle.close()
    for split in handles:
        (output / (split + ".jsonl.partial")).rename(output / (split + ".jsonl"))
    manifest = {
        "schema_version": SCHEMA_VERSION, "generator_version": __version__,
        "config": config, "config_sha256": hashlib.sha256(canonical(config).encode()).hexdigest(),
        "python_version": platform.python_version(),
        "seed_derivation": "SHA256 of canonical JSON tuples including schema version; Python Random seeded from full pair_id integer; cutoff gap uses SHA256(pair_id, cutoff-gap)",
        "world_assignments": [{"split": split, "group_id": world} for split, world, _ in worlds(config)],
        "files": [{"file": split + ".jsonl", "records": counts[split], "bytes": sizes[split],
                   "sha256": hashes[split].hexdigest()} for split in sorted(handles)],
        "source_sha256": source_hashes(),
        "provenance": {"targets": "memory_interference.oracle.answer", "source_data": "none",
                       "model_calls": 0, "model_derived_data": False,
                       "traces": "oracle.certificate computes event ID lists by filtering formal events",
                       "templates": "assistant-written fixed source-code templates; never answer annotations"},
    }
    save_json(output / "manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate")
    gen.add_argument("--config", type=Path)
    gen.add_argument("--output", type=Path, required=True)
    val = sub.add_parser("validate")
    val.add_argument("--dataset", type=Path, required=True)
    val.add_argument("--report", type=Path, required=True)
    prev = sub.add_parser("preview")
    prev.add_argument("--dataset", type=Path, required=True)
    prev.add_argument("--split", default="test")
    prev.add_argument("--index", type=int, default=0)
    scoring = sub.add_parser("score", help="score supplied predictions; never runs a model")
    scoring.add_argument("--dataset-file", type=Path, required=True)
    scoring.add_argument("--predictions", type=Path, required=True)
    scoring.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    if args.command == "generate":
        config = json.loads(args.config.read_text()) if args.config else DEFAULT_CONFIG
        manifest = generate(config, args.output)
        print(json.dumps({"result": "passed", "records": sum(f["records"] for f in manifest["files"]),
                          "bytes": sum(f["bytes"] for f in manifest["files"])}))
    elif args.command == "validate":
        manifest = json.loads((args.dataset / "manifest.json").read_text())
        expected_files = {f["file"] for f in manifest["files"]}
        if {p.name for p in args.dataset.glob("*.jsonl")} != expected_files:
            raise ValueError("dataset files differ from manifest")
        report = summarize([args.dataset / name for name in sorted(expected_files)], manifest)
        report["source_hashes_match"] = manifest["source_sha256"] == source_hashes()
        if not report["source_hashes_match"]:
            raise ValueError("source files changed since generation; regenerate or use matching source")
        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        report["peak_rss_kib_linux"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        args.report.parent.mkdir(parents=True, exist_ok=True)
        save_json(args.report, report)
        print(json.dumps({k: report[k] for k in ("result", "records", "bytes", "elapsed_seconds", "peak_rss_kib_linux")}))
    elif args.command == "score":
        report = score(args.dataset_file, args.predictions)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        save_json(args.report, report)
        print(json.dumps(report["strata"]["all"]))
    else:
        if args.split not in ("train", "validation", "test", "ood_length", "ood_delay", "ood_revisions") or args.index < 0:
            raise ValueError("invalid preview split or index")
        with (args.dataset / (args.split + ".jsonl")).open() as stream:
            for index, line in enumerate(stream):
                if index == args.index:
                    record = json.loads(line)
                    print(record["prompt"])
                    print("MECHANICAL TARGET:", canonical(record["target"]))
                    break
            else:
                raise ValueError("preview index out of range")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, AssertionError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(2)
