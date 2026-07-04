import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from proto.argument_graph import Claim, Evidence, EvidenceLevel, Stance
from proto.scoring import (
    DEFAULT_LEVEL_WEIGHTS,
    TrustWeightStore,
    argument_credibility,
    consensus_score,
    evidence_credibility,
    freshness_decay,
    meets_consensus,
)


class TestFreshnessDecay(unittest.TestCase):
    def test_undated_evidence_has_full_freshness(self):
        self.assertEqual(freshness_decay(None, date(2026, 1, 1)), 1.0)

    def test_same_day_has_full_freshness(self):
        today = date(2026, 1, 1)
        self.assertEqual(freshness_decay(today, today), 1.0)

    def test_decays_by_half_after_one_half_life(self):
        published = date(2024, 1, 1)
        as_of = published + timedelta(days=730)
        self.assertAlmostEqual(freshness_decay(published, as_of, half_life_days=730), 0.5, places=6)

    def test_older_evidence_decays_more(self):
        as_of = date(2026, 1, 1)
        recent = freshness_decay(date(2025, 6, 1), as_of)
        old = freshness_decay(date(2015, 6, 1), as_of)
        self.assertGreater(recent, old)


class TestCredibility(unittest.TestCase):
    def test_n1_weighted_higher_than_n3_same_date(self):
        as_of = date(2026, 1, 1)
        n1 = Evidence(id="e1", source_url="u", level=EvidenceLevel.N1, excerpt="x", published_date=as_of)
        n3 = Evidence(id="e2", source_url="u", level=EvidenceLevel.N3, excerpt="x", published_date=as_of)
        self.assertGreater(evidence_credibility(n1, as_of), evidence_credibility(n3, as_of))

    def test_evidence_credibility_matches_level_weight_when_fresh(self):
        as_of = date(2026, 1, 1)
        ev = Evidence(id="e1", source_url="u", level=EvidenceLevel.N2, excerpt="x", published_date=as_of)
        self.assertAlmostEqual(evidence_credibility(ev, as_of), DEFAULT_LEVEL_WEIGHTS[EvidenceLevel.N2])

    def test_argument_credibility_is_mean_of_cited_evidence(self):
        as_of = date(2026, 1, 1)
        e1 = Evidence(id="e1", source_url="u", level=EvidenceLevel.N1, excerpt="x", published_date=as_of)
        e2 = Evidence(id="e2", source_url="u", level=EvidenceLevel.N3, excerpt="x", published_date=as_of)
        claim = Claim(id="c1", author_role="advocate", text="x", stance=Stance.SUPPORT,
                      cited_evidence_ids=("e1", "e2"))
        expected = (DEFAULT_LEVEL_WEIGHTS[EvidenceLevel.N1] + DEFAULT_LEVEL_WEIGHTS[EvidenceLevel.N3]) / 2
        self.assertAlmostEqual(argument_credibility(claim, {"e1": e1, "e2": e2}, as_of), expected)

    def test_argument_credibility_zero_when_no_evidence_cited(self):
        as_of = date(2026, 1, 1)
        claim = Claim(id="c1", author_role="advocate", text="unsupported", stance=Stance.SUPPORT)
        self.assertEqual(argument_credibility(claim, {}, as_of), 0.0)


class TestConsensusScore(unittest.TestCase):
    def test_unanimous_full_support_scores_one(self):
        stances = {"advocate": 1.0, "challenger": 1.0}
        weights = {"advocate": 0.5, "challenger": 0.5}
        self.assertAlmostEqual(consensus_score(stances, weights), 1.0)

    def test_split_stance_with_equal_weights_scores_half(self):
        stances = {"advocate": 1.0, "challenger": 0.0}
        weights = {"advocate": 0.5, "challenger": 0.5}
        self.assertAlmostEqual(consensus_score(stances, weights), 0.5)

    def test_missing_weight_falls_back_to_default(self):
        stances = {"advocate": 1.0}
        self.assertAlmostEqual(consensus_score(stances, {}), 1.0)

    def test_meets_consensus_threshold(self):
        stances = {"advocate": 1.0, "challenger": 1.0}
        weights = {"advocate": 0.5, "challenger": 0.5}
        self.assertTrue(meets_consensus(stances, weights, theta=0.6))
        self.assertFalse(meets_consensus({"advocate": 0.0, "challenger": 0.0}, weights, theta=0.6))


class TestTrustWeightStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self.tmpdir.name) / "trust_weights.json"
        self.store = TrustWeightStore(path=self.path, alpha=0.5, initial_weight=0.5)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_get_returns_initial_weight_when_absent(self):
        self.assertEqual(self.store.get("advocate"), 0.5)

    def test_update_on_correct_ground_truth_increases_weight(self):
        new_weight = self.store.update_on_ground_truth("advocate", was_correct=True)
        # alpha=0.5: 0.5*1.0 + 0.5*0.5 = 0.75
        self.assertAlmostEqual(new_weight, 0.75)
        self.assertAlmostEqual(self.store.get("advocate"), 0.75)

    def test_update_on_incorrect_ground_truth_decreases_weight(self):
        new_weight = self.store.update_on_ground_truth("advocate", was_correct=False)
        # alpha=0.5: 0.5*0.0 + 0.5*0.5 = 0.25
        self.assertAlmostEqual(new_weight, 0.25)

    def test_updates_persist_across_store_instances(self):
        self.store.update_on_ground_truth("advocate", was_correct=True)
        reloaded = TrustWeightStore(path=self.path, alpha=0.5, initial_weight=0.5)
        self.assertAlmostEqual(reloaded.get("advocate"), 0.75)

    def test_all_weights_reflects_updates(self):
        self.store.update_on_ground_truth("advocate", was_correct=True)
        self.store.update_on_ground_truth("challenger", was_correct=False)
        weights = self.store.all_weights()
        self.assertIn("advocate", weights)
        self.assertIn("challenger", weights)


if __name__ == "__main__":
    unittest.main()
