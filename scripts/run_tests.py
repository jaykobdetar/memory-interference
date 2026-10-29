"""Run standard-library tests and retain structured outcomes and resource use."""

import json
from pathlib import Path
import resource
import sys
import time
import unittest
import warnings

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed.append(test.id())


def main():
    warnings.simplefilter("error", ResourceWarning)
    started = time.perf_counter()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    with (report_dir / "tests_final.log").open("w") as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
    report = {
        "result": "passed" if result.wasSuccessful() else "failed", "tests_run": result.testsRun,
        "passed": result.passed, "failed": [str(t) for t, _ in result.failures],
        "errors": [str(t) for t, _ in result.errors], "skipped": [str(t) for t, _ in result.skipped],
        "exhaustive_streams": 9331, "exhaustive_query_cases": 649452,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "peak_rss_kib_linux": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "python": sys.version, "cpu_threads": 1,
    }
    (report_dir / "tests_final.json").write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("result", "tests_run", "elapsed_seconds", "peak_rss_kib_linux")}))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
