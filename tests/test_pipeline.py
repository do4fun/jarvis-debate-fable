import json
import tempfile
import unittest
from pathlib import Path

from proto.argument_graph import Claim, Stance
from proto.checkpoint import CheckpointStore
from proto.llm_client import FakeLLMClient
from proto.logger import SessionLogger
from proto.pipeline import AgentPersona, DebateConfig, run_pipeline
from proto.scoring import TrustWeightStore


def fake_search_fn(query, base_url):
    return [{"url": "https://trusted.example/a", "domain": "trusted.example"}]


def fake_extract_fn(url):
    return {
        "raw": "<html>full page</html>",
        "text": "Title.\n\nRelevant paragraph one.\n\nRelevant paragraph two.",
        "title": "A Title",
        "published_date": None,
    }


def make_config() -> DebateConfig:
    return DebateConfig(
        advocate=AgentPersona(name="Ada", role="advocate", model="model-a"),
        challenger=AgentPersona(name="Cash", role="challenger", model="model-c"),
        judge=AgentPersona(name="Jude", role="judge", model="model-j"),
        whitelist_n1=("trusted.example",),
    )


class TestFullPipelineRun(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.checkpoints = CheckpointStore(sessions_dir=self.tmp_path / "sessions")
        self.trust_weights = TrustWeightStore(path=self.tmp_path / "trust_weights.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_full_run_produces_verdict_and_graph_with_conflict(self):
        advocate_claim = json.dumps([
            {"text": "src-1 supports X", "stance": "support", "cited_evidence_ids": ["src-1"], "rebuts": []}
        ])
        challenger_claim = json.dumps([
            {"text": "src-1 actually undermines X", "stance": "attack", "cited_evidence_ids": ["src-1"], "rebuts": []}
        ])
        judge_verdict = json.dumps({"decision": "adopt X", "reasoning": "evidence favors X", "cited_claim_ids": ["advocate-1"]})

        client = FakeLLMClient(responses=[
            "anchor query",       # [1] formulate_anchor_query
            '["src-1"]',          # [1] validate_sources
            "brainstorm notes",  # [2] brainstorming
            advocate_claim,       # [3] thesis
            challenger_claim,     # [4] antithesis
            judge_verdict,        # [7] judge pass 1
            judge_verdict,        # [7] judge pass 2
        ])

        session_logger = SessionLogger(session_id="full-run", sessions_dir=self.tmp_path / "sessions")
        result = run_pipeline(
            "Is X true?",
            make_config(),
            client,
            session_id="full-run",
            checkpoint_store=self.checkpoints,
            trust_weight_store=self.trust_weights,
            session_logger=session_logger,
            research_search_fn=fake_search_fn,
            research_extract_fn=fake_extract_fn,
            research_corpus_raw_dir=self.tmp_path / "corpus_raw",
        )

        self.assertEqual(result.verdict, "adopt X")
        self.assertEqual(len(client.calls), 7)
        self.assertEqual(len(result.graph.claims), 2)
        self.assertEqual(len(result.graph.evidence), 1)
        self.assertEqual(len(result.graph.relations), 1)  # shared-evidence opposing-stance conflict
        self.assertEqual(result.graph.relations[0].reason, "shared_evidence_opposing_stance")

        # checkpoint cleared on successful completion
        self.assertFalse(self.checkpoints.exists("full-run"))

        # full session log written and complete
        log_data = json.loads(Path(result.log_path).read_text(encoding="utf-8"))
        logged_steps = [s["step"] for s in log_data["steps"]]
        for expected_step in ("web_research", "brainstorming", "thesis", "antithesis", "synthesis"):
            self.assertIn(expected_step, logged_steps)

    def test_web_research_disabled_skips_step_and_saves_two_calls(self):
        advocate_claim = json.dumps([{"text": "x", "stance": "support", "cited_evidence_ids": [], "rebuts": []}])
        challenger_claim = json.dumps([{"text": "y", "stance": "attack", "cited_evidence_ids": [], "rebuts": []}])
        judge_verdict = json.dumps({"decision": "adopt X", "reasoning": "r", "cited_claim_ids": []})

        client = FakeLLMClient(responses=["brainstorm", advocate_claim, challenger_claim, judge_verdict, judge_verdict])
        config = make_config()
        config.enable_web_research = False

        result = run_pipeline(
            "Is X true?", config, client, session_id="no-research",
            checkpoint_store=self.checkpoints, trust_weight_store=self.trust_weights,
            session_logger=SessionLogger(session_id="no-research", sessions_dir=self.tmp_path / "sessions"),
        )

        self.assertEqual(len(client.calls), 5)  # no anchor-query / validate-sources calls
        self.assertEqual(len(result.graph.evidence), 0)


class TestPipelineResume(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        self.checkpoints = CheckpointStore(sessions_dir=self.tmp_path / "sessions")
        self.trust_weights = TrustWeightStore(path=self.tmp_path / "trust_weights.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_resume_skips_already_completed_llm_steps(self):
        session_id = "interrupted-session"
        advocate_claim = Claim(id="advocate-1", author_role="advocate", text="x", stance=Stance.SUPPORT)
        challenger_claim = Claim(id="challenger-1", author_role="challenger", text="y", stance=Stance.ATTACK,
                                  rebuts=("advocate-1",))
        pre_existing_state = {
            "brainstorming": {"notes": "notes from before the interruption"},
            "thesis": {"claims": [advocate_claim.to_dict()]},
            "antithesis": {"claims": [challenger_claim.to_dict()]},
        }
        self.checkpoints.save(session_id, "antithesis", pre_existing_state)

        judge_verdict = json.dumps({"decision": "adopt X", "reasoning": "r", "cited_claim_ids": []})
        client = FakeLLMClient(responses=[judge_verdict, judge_verdict])

        config = make_config()
        config.enable_web_research = False

        result = run_pipeline(
            "Is X true?", config, client, session_id=session_id,
            checkpoint_store=self.checkpoints, trust_weight_store=self.trust_weights,
            session_logger=SessionLogger(session_id=session_id, sessions_dir=self.tmp_path / "sessions"),
        )

        # Only the 2 judge calls happen -- brainstorming/thesis/antithesis are
        # not regenerated because they were already checkpointed.
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(result.verdict, "adopt X")
        self.assertEqual(len(result.graph.relations), 1)  # explicit rebuttal survives the resume

        log_data = json.loads(Path(result.log_path).read_text(encoding="utf-8"))
        logged_steps = [s["step"] for s in log_data["steps"]]
        # steps completed before the interruption are still present in the final log
        self.assertIn("brainstorming", logged_steps)
        self.assertIn("thesis", logged_steps)
        self.assertIn("antithesis", logged_steps)
        self.assertIn("synthesis", logged_steps)

        self.assertFalse(self.checkpoints.exists(session_id))  # cleared once the resumed run completes


if __name__ == "__main__":
    unittest.main()
