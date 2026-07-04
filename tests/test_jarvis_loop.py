import json
import tempfile
import unittest
from pathlib import Path

from proto.checkpoint import CheckpointStore
from proto.jarvis_loop import DEFAULT_LATENCY_THRESHOLD_S, answer_or_debate, default_router, meets_latency_threshold
from proto.llm_client import FakeLLMClient
from proto.logger import SessionLogger
from proto.pipeline import AgentPersona, DebateConfig
from proto.scoring import TrustWeightStore


def make_config(enable_web_research: bool = False) -> DebateConfig:
    return DebateConfig(
        advocate=AgentPersona(name="Ada", role="advocate", model="model-a"),
        challenger=AgentPersona(name="Cash", role="challenger", model="model-c"),
        judge=AgentPersona(name="Jude", role="judge", model="model-j"),
        enable_web_research=enable_web_research,
    )


class TestAnswerOrDebate(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.checkpoints = CheckpointStore(sessions_dir=self.tmp_path / "sessions")
        self.trust_weights = TrustWeightStore(path=self.tmp_path / "trust_weights.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _pipeline_kwargs(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "checkpoint_store": self.checkpoints,
            "trust_weight_store": self.trust_weights,
            "session_logger": SessionLogger(session_id=session_id, sessions_dir=self.tmp_path / "sessions"),
        }

    def test_default_router_always_answers_directly(self):
        client = FakeLLMClient(responses=["a direct answer"])
        result = answer_or_debate("What is X?", client, make_config(), "direct-model")

        self.assertFalse(result.routed_to_debate)
        self.assertIsNone(result.pipeline_result)
        self.assertEqual(result.answer, "a direct answer")
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0]["model"], "direct-model")

    def test_router_returning_true_triggers_full_debate(self):
        advocate_claim = json.dumps([{"text": "x", "stance": "support", "cited_evidence_ids": [], "rebuts": []}])
        challenger_claim = json.dumps([{"text": "y", "stance": "attack", "cited_evidence_ids": [], "rebuts": []}])
        judge_verdict = json.dumps({"decision": "adopt X", "reasoning": "r", "cited_claim_ids": []})
        client = FakeLLMClient(responses=["brainstorm", advocate_claim, challenger_claim, judge_verdict, judge_verdict])

        result = answer_or_debate(
            "débat : Is X true?", client, make_config(), "direct-model",
            router=lambda q: True, **self._pipeline_kwargs("debate-session"),
        )

        self.assertTrue(result.routed_to_debate)
        self.assertIsNotNone(result.pipeline_result)
        self.assertEqual(result.answer, "adopt X")
        self.assertEqual(len(client.calls), 5)  # brainstorming + thesis + antithesis + 2 judge passes, no research

    def test_web_research_forced_off_even_if_config_enables_it(self):
        advocate_claim = json.dumps([{"text": "x", "stance": "support", "cited_evidence_ids": [], "rebuts": []}])
        challenger_claim = json.dumps([{"text": "y", "stance": "attack", "cited_evidence_ids": [], "rebuts": []}])
        judge_verdict = json.dumps({"decision": "adopt X", "reasoning": "r", "cited_claim_ids": []})
        client = FakeLLMClient(responses=["brainstorm", advocate_claim, challenger_claim, judge_verdict, judge_verdict])

        config_with_research_enabled = make_config(enable_web_research=True)
        result = answer_or_debate(
            "débat : Is X true?", client, config_with_research_enabled, "direct-model",
            router=lambda q: True, **self._pipeline_kwargs("debate-session-2"),
        )

        self.assertTrue(result.routed_to_debate)
        self.assertEqual(len(client.calls), 5)  # still no anchor-query/validate-sources calls
        self.assertEqual(len(result.pipeline_result.graph.evidence), 0)
        # the caller's original config object is untouched (no in-place mutation)
        self.assertTrue(config_with_research_enabled.enable_web_research)

    def test_latency_is_recorded(self):
        client = FakeLLMClient(responses=["answer"])
        result = answer_or_debate("What is X?", client, make_config(), "direct-model")
        self.assertGreaterEqual(result.latency_s, 0.0)

    def test_default_router_is_a_placeholder_that_never_debates(self):
        self.assertFalse(default_router("any question at all"))
        self.assertFalse(default_router("débat : even a debate-shaped question"))


class TestMeetsLatencyThreshold(unittest.TestCase):
    def test_under_threshold_passes(self):
        self.assertTrue(meets_latency_threshold(1.0, threshold_s=5.0))

    def test_over_threshold_fails(self):
        self.assertFalse(meets_latency_threshold(10.0, threshold_s=5.0))

    def test_exactly_at_threshold_passes(self):
        self.assertTrue(meets_latency_threshold(5.0, threshold_s=5.0))

    def test_default_threshold_is_used_when_omitted(self):
        self.assertTrue(meets_latency_threshold(DEFAULT_LATENCY_THRESHOLD_S - 0.1))
        self.assertFalse(meets_latency_threshold(DEFAULT_LATENCY_THRESHOLD_S + 0.1))


if __name__ == "__main__":
    unittest.main()
