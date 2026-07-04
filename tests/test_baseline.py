import unittest

from proto.baseline import run_self_consistency
from proto.llm_client import FakeLLMClient


class TestSelfConsistency(unittest.TestCase):
    def test_majority_vote_wins(self):
        client = FakeLLMClient(responses=["A", "A", "B"])
        result = run_self_consistency(client, "model", "prompt", n_samples=3)
        self.assertEqual(result["majority"], "A")
        self.assertEqual(result["votes"], 2)
        self.assertEqual(result["n_samples"], 3)

    def test_samples_exactly_n_times_matching_debate_budget(self):
        client = FakeLLMClient(responses=["A"] * 6)
        run_self_consistency(client, "model", "prompt", n_samples=6)
        self.assertEqual(len(client.calls), 6)

    def test_rejects_non_positive_sample_count(self):
        client = FakeLLMClient(responses=[])
        with self.assertRaises(ValueError):
            run_self_consistency(client, "model", "prompt", n_samples=0)


if __name__ == "__main__":
    unittest.main()
