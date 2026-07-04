import tempfile
import unittest
from pathlib import Path

from proto.fact_verification import ClaimVerdict
from proto.verdict_store import VerdictStore


def make_verdict(claim_id="c1", evidence_hashes=None):
    return ClaimVerdict(
        claim_id=claim_id, label="soutenu", confidence=0.9, reasoning="r",
        cited_evidence_ids=("e1",),
        evidence_hashes={"e1": "hash1"} if evidence_hashes is None else evidence_hashes,
    )


class TestVerdictStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = VerdictStore(path=Path(self.tmpdir.name) / "verdicts.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_save_then_get_round_trips(self):
        verdict = make_verdict()
        self.store.save(verdict)
        self.assertEqual(self.store.get("c1"), verdict)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.store.get("missing"))

    def test_all_claim_ids(self):
        self.store.save(make_verdict("c1"))
        self.store.save(make_verdict("c2"))
        self.assertEqual(set(self.store.all_claim_ids()), {"c1", "c2"})

    def test_unchanged_hash_is_not_invalidated(self):
        self.store.save(make_verdict("c1", evidence_hashes={"e1": "hash1"}))
        stale = self.store.invalidate_stale({"e1": "hash1"})
        self.assertEqual(stale, [])
        self.assertIsNotNone(self.store.get("c1"))

    def test_changed_hash_invalidates_verdict(self):
        self.store.save(make_verdict("c1", evidence_hashes={"e1": "hash1"}))
        stale = self.store.invalidate_stale({"e1": "hash2-after-recrawl"})
        self.assertEqual(stale, ["c1"])
        self.assertIsNone(self.store.get("c1"))

    def test_evidence_id_missing_from_current_hashes_invalidates(self):
        self.store.save(make_verdict("c1", evidence_hashes={"e1": "hash1"}))
        stale = self.store.invalidate_stale({})  # e.g. the page was removed from the corpus
        self.assertEqual(stale, ["c1"])

    def test_verdict_with_no_evidence_hashes_is_never_invalidated(self):
        self.store.save(make_verdict("c1", evidence_hashes={}))
        stale = self.store.invalidate_stale({})
        self.assertEqual(stale, [])
        self.assertIsNotNone(self.store.get("c1"))

    def test_only_stale_verdicts_are_removed(self):
        self.store.save(make_verdict("c1", evidence_hashes={"e1": "hash1"}))
        self.store.save(make_verdict("c2", evidence_hashes={"e2": "hash2"}))
        stale = self.store.invalidate_stale({"e1": "hash1", "e2": "CHANGED"})
        self.assertEqual(stale, ["c2"])
        self.assertIsNotNone(self.store.get("c1"))
        self.assertIsNone(self.store.get("c2"))


if __name__ == "__main__":
    unittest.main()
