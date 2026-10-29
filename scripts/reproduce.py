"""Recompute every JSONL byte hash without writing a second corpus."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import resource
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from memory_interference.generator import canonical, records
from memory_interference.__main__ import source_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    manifest = json.loads((args.dataset / "manifest.json").read_text())
    hashes, counts, sizes = {}, Counter(), Counter()
    for r in records(manifest["config"]):
        filename = r["split"] + ".jsonl"
        raw = (canonical(r) + "\n").encode()
        hashes.setdefault(filename, hashlib.sha256()).update(raw)
        counts[filename] += 1; sizes[filename] += len(raw)
    observed = [{"file": filename, "sha256": hashes[filename].hexdigest(), "records": counts[filename],
                 "bytes": sizes[filename]} for filename in sorted(hashes)]
    passed = observed == manifest["files"] and source_hashes() == manifest["source_sha256"]
    report = {"result": "passed" if passed else "failed", "files": observed,
              "source_hashes_match": source_hashes() == manifest["source_sha256"],
              "elapsed_seconds": round(time.perf_counter() - started, 3),
              "peak_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"result": report["result"], "files": len(observed), "records": sum(counts.values())}))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
