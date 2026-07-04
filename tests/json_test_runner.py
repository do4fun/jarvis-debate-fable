"""Test runner that logs each completed test at DEBUG level and writes a
JSON summary to `logs/test_results_<timestamp>.json` -- so a run leaves a
machine-readable trace of what ran and what passed/failed, not just stdout
that scrolls away.

Entry point: `python run_tests.py` (repo root) -- this module holds the
reusable, unit-testable pieces; `run_tests.py` is a thin CLI wrapper.
"""
from __future__ import annotations

import json
import logging
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOGS_DIR = Path("logs")

logger = logging.getLogger("jarvis_debate_fable.tests")


class JSONTestResult(unittest.TextTestResult):
    """Collects a JSON-serializable record per test (id, outcome, duration,
    failure/error detail) in addition to unittest's normal reporting, and
    logs each completion at DEBUG level as it happens."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.test_records: list[dict] = []
        self._start_times: dict[unittest.TestCase, float] = {}

    def startTest(self, test) -> None:
        super().startTest(test)
        self._start_times[test] = time.monotonic()
        logger.debug("START %s", test.id())

    def _record(self, test, outcome: str, detail: str | None = None) -> None:
        duration = time.monotonic() - self._start_times.get(test, time.monotonic())
        record = {"test": test.id(), "outcome": outcome, "duration_s": round(duration, 4)}
        if detail:
            record["detail"] = detail
        self.test_records.append(record)
        logger.debug("DONE %s -> %s (%.4fs)", test.id(), outcome, duration)

    def addSuccess(self, test) -> None:
        super().addSuccess(test)
        self._record(test, "pass")

    def addFailure(self, test, err) -> None:
        super().addFailure(test, err)
        self._record(test, "fail", detail=self._exc_info_to_string(err, test))

    def addError(self, test, err) -> None:
        super().addError(test, err)
        self._record(test, "error", detail=self._exc_info_to_string(err, test))

    def addSkip(self, test, reason) -> None:
        super().addSkip(test, reason)
        self._record(test, "skip", detail=reason)

    def addExpectedFailure(self, test, err) -> None:
        super().addExpectedFailure(test, err)
        self._record(test, "expected_failure", detail=self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test) -> None:
        super().addUnexpectedSuccess(test)
        self._record(test, "unexpected_success")


def build_summary(result: JSONTestResult, started_at: datetime, finished_at: datetime) -> dict:
    return {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_s": round((finished_at - started_at).total_seconds(), 4),
        "totals": {
            "run": result.testsRun,
            "passed": result.testsRun - len(result.failures) - len(result.errors) - len(result.skipped),
            "failures": len(result.failures),
            "errors": len(result.errors),
            "skipped": len(result.skipped),
        },
        "tests": result.test_records,
    }


def write_summary(summary: dict, logs_dir: Path, timestamp: str) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    path = logs_dir / f"test_results_{timestamp}.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def configure_logging(log_file: Path) -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler()],
        force=True,  # re-configure even if something else already called basicConfig
    )


def run(start_dir: str = "tests", logs_dir: Path | str | None = None) -> int:
    logs_dir = Path(logs_dir) if logs_dir else DEFAULT_LOGS_DIR
    started_at = datetime.now(timezone.utc)
    timestamp = started_at.strftime("%Y%m%dT%H%M%SZ")

    logs_dir.mkdir(parents=True, exist_ok=True)
    log_file = logs_dir / f"test_run_{timestamp}.log"
    configure_logging(log_file)

    suite = unittest.TestLoader().discover(start_dir=start_dir)
    runner = unittest.TextTestRunner(resultclass=JSONTestResult, verbosity=2)
    result = runner.run(suite)

    finished_at = datetime.now(timezone.utc)
    summary = build_summary(result, started_at, finished_at)
    json_path = write_summary(summary, logs_dir, timestamp)
    logger.debug("Wrote JSON test results to %s", json_path)
    print(f"\nJSON results: {json_path}\nText log: {log_file}")

    return 0 if result.wasSuccessful() else 1
