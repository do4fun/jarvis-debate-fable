import json
import unittest

from proto.argument_graph import Evidence, EvidenceLevel, Stance
from proto.debate_local import DebateParsingError, double_pass_judge, generate_position
from proto.llm_client import FakeLLMClient


def make_evidence():
    return [Evidence(id="e1", source_url="https://example.org", level=EvidenceLevel.N1, excerpt="fact one")]


class TestGeneratePosition(unittest.TestCase):
    def test_parses_valid_claims(self):
        response = json.dumps([
            {"text": "Evidence e1 supports X", "stance": "support", "cited_evidence_ids": ["e1"], "rebuts": []},
        ])
        client = FakeLLMClient(responses=[response])
        claims = generate_position(client, "test-model", "advocate", "Is X true?", make_evidence(), "advocate")

        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0].id, "advocate-1")
        self.assertEqual(claims[0].author_role, "advocate")
        self.assertEqual(claims[0].stance, Stance.SUPPORT)
        self.assertEqual(claims[0].cited_evidence_ids, ("e1",))

    def test_invalid_json_raises_debate_parsing_error(self):
        client = FakeLLMClient(responses=["not json"])
        with self.assertRaises(DebateParsingError):
            generate_position(client, "test-model", "advocate", "Q", make_evidence(), "advocate")

    def test_missing_required_field_raises(self):
        response = json.dumps([{"text": "no stance field"}])
        client = FakeLLMClient(responses=[response])
        with self.assertRaises(DebateParsingError):
            generate_position(client, "test-model", "advocate", "Q", make_evidence(), "advocate")

    def test_round_1_has_no_opposing_claims_in_prompt_by_default(self):
        response = json.dumps([{"text": "x", "stance": "support", "cited_evidence_ids": [], "rebuts": []}])
        client = FakeLLMClient(responses=[response])
        generate_position(client, "test-model", "advocate", "Q", make_evidence(), "advocate")
        self.assertNotIn("Opposing position", client.calls[0]["prompt"])


class TestDoublePassJudge(unittest.TestCase):
    def test_agreement_across_passes_yields_that_decision(self):
        agree = json.dumps({"decision": "adopt X", "reasoning": "strong evidence", "cited_claim_ids": ["advocate-1"]})
        client = FakeLLMClient(responses=[agree, agree])
        pass_1, pass_2, verdict = double_pass_judge(client, "judge-model", "Q", [], [], {}, {})
        self.assertEqual(verdict, "adopt X")
        self.assertEqual(pass_1.order, "advocate_first")
        self.assertEqual(pass_2.order, "challenger_first")

    def test_divergence_across_passes_forces_indecidable(self):
        first = json.dumps({"decision": "adopt X", "reasoning": "r1", "cited_claim_ids": []})
        second = json.dumps({"decision": "reject X", "reasoning": "r2", "cited_claim_ids": []})
        client = FakeLLMClient(responses=[first, second])
        _, _, verdict = double_pass_judge(client, "judge-model", "Q", [], [], {}, {})
        self.assertIn("indécidable", verdict)


if __name__ == "__main__":
    unittest.main()
