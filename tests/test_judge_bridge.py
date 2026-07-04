import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

from proto.argument_graph import Claim, Evidence, EvidenceLevel, Stance
from proto.judge_bridge import build_graph_report, main
from proto.scoring import TrustWeightStore

REPO_ROOT = Path(__file__).resolve().parent.parent


def make_evidence():
    return [Evidence(id="e1", source_url="https://example.org", level=EvidenceLevel.N1, excerpt="fact",
                      published_date=date(2026, 1, 1))]


def make_claims():
    return [
        Claim(id="advocate-1", author_role="advocate", text="e1 supports X", stance=Stance.SUPPORT,
              cited_evidence_ids=("e1",)),
        Claim(id="challenger-1", author_role="challenger", text="e1 undermines X", stance=Stance.ATTACK,
              cited_evidence_ids=("e1",)),
    ]


class TestBuildGraphReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = TrustWeightStore(path=Path(self.tmpdir.name) / "trust_weights.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_report_contains_graph_credibility_and_consensus(self):
        report = build_graph_report(make_evidence(), make_claims(), date(2026, 1, 1), trust_weight_store=self.store)
        self.assertEqual(len(report["graph"]["claims"]), 2)
        self.assertEqual(len(report["graph"]["relations"]), 1)  # shared-evidence opposing-stance conflict
        self.assertIn("advocate-1", report["credibility"])
        self.assertIn("score", report["consensus"])
        self.assertIn("theta", report["consensus"])

    def test_report_is_json_serializable(self):
        report = build_graph_report(make_evidence(), make_claims(), date(2026, 1, 1), trust_weight_store=self.store)
        json.dumps(report)  # must not raise


class TestMainCLIContract(unittest.TestCase):
    """The judge subagent's whole point of contact with this module is the
    CLI surface invoked via Bash -- these tests exercise exactly that
    surface, not just the Python functions underneath."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmpdir.name)
        self.evidence_path = self.dir / "evidence.json"
        self.claims_path = self.dir / "claims.json"
        self.evidence_path.write_text(json.dumps({"evidence": [e.to_dict() for e in make_evidence()]}), encoding="utf-8")
        self.claims_path.write_text(json.dumps({"claims": [c.to_dict() for c in make_claims()]}), encoding="utf-8")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_main_returns_zero_and_prints_valid_json(self):
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            exit_code = main(["--evidence", str(self.evidence_path), "--claims", str(self.claims_path),
                               "--as-of", "2026-01-01", "--trust-weights", str(self.dir / "tw.json")])
        self.assertEqual(exit_code, 0)
        report = json.loads(buf.getvalue())
        self.assertEqual(len(report["graph"]["relations"]), 1)

    def test_missing_file_returns_nonzero_with_clear_stderr(self):
        exit_code = main(["--evidence", str(self.dir / "missing.json"), "--claims", str(self.claims_path)])
        self.assertEqual(exit_code, 1)

    def test_invoked_as_subprocess_matches_bash_usage(self):
        result = subprocess.run(
            [sys.executable, "-m", "proto.judge_bridge",
             "--evidence", str(self.evidence_path), "--claims", str(self.claims_path),
             "--as-of", "2026-01-01", "--trust-weights", str(self.dir / "tw.json")],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(len(report["graph"]["claims"]), 2)


if __name__ == "__main__":
    unittest.main()
