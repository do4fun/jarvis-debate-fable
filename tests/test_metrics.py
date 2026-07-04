import unittest

from proto.fact_verification import ClaimVerdict
from proto.metrics import GroundTruthClaim, error_detection_precision_recall, inverifiable_routing_accuracy, post_cutoff_false_negative_rate


def verdict(claim_id, label):
    return ClaimVerdict(claim_id=claim_id, label=label, confidence=1.0, reasoning="")


class TestErrorDetectionPrecisionRecall(unittest.TestCase):
    def test_perfect_predictions_score_one(self):
        predictions = [verdict("c1", "contredit"), verdict("c2", "soutenu")]
        ground_truth = [GroundTruthClaim("c1", "contredit"), GroundTruthClaim("c2", "soutenu")]
        result = error_detection_precision_recall(predictions, ground_truth)
        self.assertEqual(result["precision"], 1.0)
        self.assertEqual(result["recall"], 1.0)

    def test_false_positive_lowers_precision_only(self):
        predictions = [verdict("c1", "contredit"), verdict("c2", "contredit")]
        ground_truth = [GroundTruthClaim("c1", "contredit"), GroundTruthClaim("c2", "soutenu")]
        result = error_detection_precision_recall(predictions, ground_truth)
        self.assertEqual(result["precision"], 0.5)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(result["fp"], 1)

    def test_false_negative_lowers_recall_only(self):
        predictions = [verdict("c1", "soutenu"), verdict("c2", "soutenu")]
        ground_truth = [GroundTruthClaim("c1", "contredit"), GroundTruthClaim("c2", "soutenu")]
        result = error_detection_precision_recall(predictions, ground_truth)
        self.assertEqual(result["recall"], 0.0)
        self.assertEqual(result["fn"], 1)

    def test_unmatched_predictions_are_ignored(self):
        predictions = [verdict("unknown-claim", "contredit")]
        ground_truth = [GroundTruthClaim("c1", "contredit")]
        result = error_detection_precision_recall(predictions, ground_truth)
        self.assertEqual(result, {"precision": 0.0, "recall": 0.0, "tp": 0, "fp": 0, "fn": 1, "tn": 0})

    def test_empty_inputs_do_not_divide_by_zero(self):
        result = error_detection_precision_recall([], [])
        self.assertEqual(result["precision"], 0.0)
        self.assertEqual(result["recall"], 0.0)


class TestInverifiableRoutingAccuracy(unittest.TestCase):
    def test_correctly_routed_no_evidence_claim_scores_one(self):
        predictions = [verdict("c1", "invérifiable")]
        ground_truth = [GroundTruthClaim("c1", "invérifiable", has_evidence=False)]
        self.assertEqual(inverifiable_routing_accuracy(predictions, ground_truth), 1.0)

    def test_fabricated_verdict_scores_zero(self):
        predictions = [verdict("c1", "soutenu")]  # fabricated a verdict despite no evidence
        ground_truth = [GroundTruthClaim("c1", "invérifiable", has_evidence=False)]
        self.assertEqual(inverifiable_routing_accuracy(predictions, ground_truth), 0.0)

    def test_claims_with_evidence_are_excluded_from_denominator(self):
        predictions = [verdict("c1", "soutenu")]
        ground_truth = [GroundTruthClaim("c1", "soutenu", has_evidence=True)]
        self.assertEqual(inverifiable_routing_accuracy(predictions, ground_truth), 0.0)

    def test_no_no_evidence_claims_returns_zero_not_nan(self):
        self.assertEqual(inverifiable_routing_accuracy([], []), 0.0)


class TestPostCutoffFalseNegativeRate(unittest.TestCase):
    def test_missed_post_cutoff_error_counted(self):
        predictions = [verdict("c1", "soutenu")]  # should have been "contredit"
        ground_truth = [GroundTruthClaim("c1", "contredit", is_post_cutoff=True)]
        self.assertEqual(post_cutoff_false_negative_rate(predictions, ground_truth), 1.0)

    def test_caught_post_cutoff_error_not_counted(self):
        predictions = [verdict("c1", "contredit")]
        ground_truth = [GroundTruthClaim("c1", "contredit", is_post_cutoff=True)]
        self.assertEqual(post_cutoff_false_negative_rate(predictions, ground_truth), 0.0)

    def test_pre_cutoff_claims_excluded(self):
        predictions = [verdict("c1", "soutenu")]
        ground_truth = [GroundTruthClaim("c1", "contredit", is_post_cutoff=False)]
        self.assertEqual(post_cutoff_false_negative_rate(predictions, ground_truth), 0.0)

    def test_no_post_cutoff_errors_returns_zero_not_nan(self):
        self.assertEqual(post_cutoff_false_negative_rate([], []), 0.0)


if __name__ == "__main__":
    unittest.main()
