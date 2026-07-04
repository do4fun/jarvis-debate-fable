import json
import tempfile
import unittest
from pathlib import Path

from proto.pattern_report import PatternEntry, build_pattern_report, default_patterns, write_pattern_report
from proto.scoring import TrustWeightStore


class TestDefaultPatterns(unittest.TestCase):
    def test_all_default_patterns_are_pending(self):
        patterns = default_patterns()
        self.assertTrue(patterns)
        self.assertTrue(all(p.status == "en_attente" for p in patterns))

    def test_every_pattern_cites_at_least_one_source_file(self):
        for p in default_patterns():
            self.assertTrue(p.source_files, msg=f"{p.name} has no source_files")

    def test_pattern_entry_round_trips_to_dict(self):
        entry = PatternEntry("test", "0.1", "retenu", corrections=("F1",), source_files=("proto/x.py",), rationale="r")
        d = entry.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["corrections"], ["F1"])
        self.assertEqual(d["source_files"], ["proto/x.py"])


class TestBuildPatternReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = TrustWeightStore(path=Path(self.tmpdir.name) / "trust_weights.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_report_includes_patterns_and_trust_weight_sections(self):
        report = build_pattern_report(trust_weight_store=self.store)
        self.assertIn("generated_at", report)
        self.assertIn("patterns", report)
        self.assertIn("trust_weights_final", report)
        self.assertIn("trust_weights_drift", report)
        self.assertEqual(report["trust_weights_final"], {})
        self.assertEqual(report["trust_weights_drift"], [])

    def test_report_reflects_real_trust_weight_updates(self):
        self.store.update_on_ground_truth("advocate", was_correct=True)
        report = build_pattern_report(trust_weight_store=self.store)
        self.assertIn("advocate", report["trust_weights_final"])
        self.assertEqual(len(report["trust_weights_drift"]), 1)

    def test_custom_pattern_list_overrides_default(self):
        custom = [PatternEntry("custom", "0.1", "retenu")]
        report = build_pattern_report(patterns=custom, trust_weight_store=self.store)
        self.assertEqual(len(report["patterns"]), 1)
        self.assertEqual(report["patterns"][0]["name"], "custom")

    def test_report_is_json_serializable(self):
        report = build_pattern_report(trust_weight_store=self.store)
        json.dumps(report)  # must not raise


class TestWritePatternReport(unittest.TestCase):
    def test_writes_file_and_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "pattern_report.json"
            written = write_pattern_report({"a": 1}, path)
            self.assertTrue(written.exists())
            self.assertEqual(json.loads(written.read_text(encoding="utf-8")), {"a": 1})


if __name__ == "__main__":
    unittest.main()
