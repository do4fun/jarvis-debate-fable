import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from tests.json_test_runner import JSONTestResult, build_summary, write_summary

# The dummy TestCase classes below exist only to exercise JSONTestResult's
# pass/fail/error/skip handling. They are defined inside factory functions
# (not at module scope) on purpose: `unittest discover` finds TestCase
# subclasses via module-level attributes, and a class returned from a
# function is never a module attribute -- so these synthetic
# fail/error/skip cases never get picked up and run as if they were real
# tests of this project when the outer suite runs `python -m unittest
# discover -s tests`.


def _dummy_pass():
    class _DummyPass(unittest.TestCase):
        def test_ok(self):
            pass

    return _DummyPass


def _dummy_fail():
    class _DummyFail(unittest.TestCase):
        def test_fails(self):
            self.assertEqual(1, 2)

    return _DummyFail


def _dummy_error():
    class _DummyError(unittest.TestCase):
        def test_errors(self):
            raise RuntimeError("boom")

    return _DummyError


def _dummy_skip():
    class _DummySkip(unittest.TestCase):
        def test_skipped(self):
            self.skipTest("not applicable")

    return _DummySkip


def _run_suite(suite: unittest.TestSuite) -> JSONTestResult:
    runner = unittest.TextTestRunner(resultclass=JSONTestResult, stream=StringIO(), verbosity=0)
    return runner.run(suite)


class TestJSONTestResultRecording(unittest.TestCase):
    def test_records_a_passing_test(self):
        suite = unittest.TestLoader().loadTestsFromTestCase(_dummy_pass())
        result = _run_suite(suite)
        self.assertEqual(len(result.test_records), 1)
        record = result.test_records[0]
        self.assertTrue(record["test"].endswith("_DummyPass.test_ok"))
        self.assertEqual(record["outcome"], "pass")
        self.assertIn("duration_s", record)
        self.assertNotIn("detail", record)

    def test_records_a_failure_with_detail(self):
        suite = unittest.TestLoader().loadTestsFromTestCase(_dummy_fail())
        result = _run_suite(suite)
        record = result.test_records[0]
        self.assertEqual(record["outcome"], "fail")
        self.assertIn("detail", record)
        self.assertIn("AssertionError", record["detail"])

    def test_records_an_error_with_detail(self):
        suite = unittest.TestLoader().loadTestsFromTestCase(_dummy_error())
        result = _run_suite(suite)
        record = result.test_records[0]
        self.assertEqual(record["outcome"], "error")
        self.assertIn("RuntimeError", record["detail"])

    def test_records_a_skip_with_reason(self):
        suite = unittest.TestLoader().loadTestsFromTestCase(_dummy_skip())
        result = _run_suite(suite)
        record = result.test_records[0]
        self.assertEqual(record["outcome"], "skip")
        self.assertEqual(record["detail"], "not applicable")

    def test_mixed_suite_records_all_outcomes_independently(self):
        suite = unittest.TestSuite()
        for case in (_dummy_pass(), _dummy_fail(), _dummy_error(), _dummy_skip()):
            suite.addTests(unittest.TestLoader().loadTestsFromTestCase(case))
        result = _run_suite(suite)
        outcomes = {r["outcome"] for r in result.test_records}
        self.assertEqual(outcomes, {"pass", "fail", "error", "skip"})
        self.assertEqual(result.testsRun, 4)


class TestBuildSummary(unittest.TestCase):
    def test_totals_match_result_counts(self):
        suite = unittest.TestSuite()
        for case in (_dummy_pass(), _dummy_fail(), _dummy_error(), _dummy_skip()):
            suite.addTests(unittest.TestLoader().loadTestsFromTestCase(case))
        result = _run_suite(suite)
        started = datetime(2026, 1, 1, tzinfo=timezone.utc)
        finished = started + timedelta(seconds=2)

        summary = build_summary(result, started, finished)

        self.assertEqual(summary["totals"], {"run": 4, "passed": 1, "failures": 1, "errors": 1, "skipped": 1})
        self.assertEqual(summary["duration_s"], 2.0)
        self.assertEqual(len(summary["tests"]), 4)

    def test_summary_is_json_serializable(self):
        suite = unittest.TestLoader().loadTestsFromTestCase(_dummy_pass())
        result = _run_suite(suite)
        summary = build_summary(result, datetime.now(timezone.utc), datetime.now(timezone.utc))
        json.dumps(summary)  # must not raise


class TestWriteSummary(unittest.TestCase):
    def test_writes_json_file_named_with_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp)
            path = write_summary({"totals": {"run": 1}}, logs_dir, "20260101T000000Z")
            self.assertTrue(path.exists())
            self.assertEqual(path.name, "test_results_20260101T000000Z.json")
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"totals": {"run": 1}})

    def test_creates_logs_dir_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "nested" / "logs"
            self.assertFalse(logs_dir.exists())
            write_summary({}, logs_dir, "ts")
            self.assertTrue(logs_dir.exists())


if __name__ == "__main__":
    unittest.main()
