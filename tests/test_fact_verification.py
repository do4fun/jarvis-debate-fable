import json
import unittest
from datetime import date

from proto.argument_graph import EvidenceLevel
from proto.chunk_and_index import ChunkMetadata
from proto.fact_verification import (
    FactVerificationError,
    aggregate_chunk,
    chunk_to_evidence,
    decompose_into_claims,
    double_pass_claim_judge,
    pre_debate_filter,
    verify_claim,
    ClaimVerdict,
)
from proto.llm_client import FakeLLMClient


def make_chunk(chunk_id="c1", level=EvidenceLevel.N1, text="Some evidence text.", content_hash="hash1"):
    return ChunkMetadata(chunk_id=chunk_id, source_url="https://example.org", domain="example.org",
                         language="en", level=level, text=text, published_date=date(2026, 1, 1),
                         content_hash=content_hash)


class TestDecomposeIntoClaims(unittest.TestCase):
    def test_parses_list_of_strings(self):
        client = FakeLLMClient(responses=['["claim one", "claim two"]'])
        claims = decompose_into_claims(client, "model", "some chunk text")
        self.assertEqual(claims, ["claim one", "claim two"])

    def test_invalid_json_raises(self):
        client = FakeLLMClient(responses=["not json"])
        with self.assertRaises(FactVerificationError):
            decompose_into_claims(client, "model", "text")

    def test_non_list_raises(self):
        client = FakeLLMClient(responses=['{"not": "a list"}'])
        with self.assertRaises(FactVerificationError):
            decompose_into_claims(client, "model", "text")


class TestChunkToEvidence(unittest.TestCase):
    def test_conversion_preserves_fields(self):
        chunk = make_chunk()
        evidence = chunk_to_evidence(chunk)
        self.assertEqual(evidence.id, chunk.chunk_id)
        self.assertEqual(evidence.level, chunk.level)
        self.assertEqual(evidence.excerpt, chunk.text)
        self.assertEqual(evidence.content_hash, chunk.content_hash)


class TestPreDebateFilter(unittest.TestCase):
    def test_no_evidence_is_inverifiable_without_llm_call(self):
        client = FakeLLMClient(responses=["should not be consumed"])
        result = pre_debate_filter(client, "model", "claim text", [])
        self.assertTrue(result.confident)
        self.assertEqual(result.label, "invérifiable")
        self.assertEqual(len(client.calls), 0)

    def test_confident_result_parsed(self):
        response = json.dumps({"confident": True, "label": "soutenu", "reasoning": "clear match",
                                "cited_evidence_ids": ["c1"]})
        client = FakeLLMClient(responses=[response])
        result = pre_debate_filter(client, "model", "claim", [make_chunk()])
        self.assertTrue(result.confident)
        self.assertEqual(result.label, "soutenu")

    def test_uncertain_result_parsed(self):
        response = json.dumps({"confident": False, "label": None, "reasoning": "ambiguous", "cited_evidence_ids": []})
        client = FakeLLMClient(responses=[response])
        result = pre_debate_filter(client, "model", "claim", [make_chunk()])
        self.assertFalse(result.confident)
        self.assertIsNone(result.label)

    def test_malformed_output_raises(self):
        client = FakeLLMClient(responses=["not json"])
        with self.assertRaises(FactVerificationError):
            pre_debate_filter(client, "model", "claim", [make_chunk()])


class TestDoublePassClaimJudge(unittest.TestCase):
    def test_agreement_yields_averaged_confidence(self):
        p1 = json.dumps({"label": "soutenu", "confidence": 0.8, "reasoning": "r1", "cited_claim_ids": ["affirmateur-1"]})
        p2 = json.dumps({"label": "soutenu", "confidence": 0.6, "reasoning": "r2", "cited_claim_ids": ["affirmateur-1"]})
        client = FakeLLMClient(responses=[p1, p2])
        _, _, final = double_pass_claim_judge(client, "model", "claim", [], [], {}, 0.5)
        self.assertEqual(final.label, "soutenu")
        self.assertAlmostEqual(final.confidence, 0.7)

    def test_divergence_forces_inverifiable(self):
        p1 = json.dumps({"label": "soutenu", "confidence": 0.9, "reasoning": "r1", "cited_claim_ids": []})
        p2 = json.dumps({"label": "contredit", "confidence": 0.9, "reasoning": "r2", "cited_claim_ids": []})
        client = FakeLLMClient(responses=[p1, p2])
        _, _, final = double_pass_claim_judge(client, "model", "claim", [], [], {}, 0.5)
        self.assertEqual(final.label, "invérifiable")
        self.assertEqual(final.confidence, 0.0)


class TestVerifyClaim(unittest.TestCase):
    def test_no_evidence_short_circuits_with_no_llm_calls(self):
        client = FakeLLMClient(responses=["unused"])
        verdict = verify_claim(client, "m1", "m2", "m3", "claim-1", "the sky is blue", [])
        self.assertEqual(verdict.label, "invérifiable")
        self.assertEqual(len(client.calls), 0)

    def test_confident_filter_skips_debate_entirely(self):
        filter_response = json.dumps({"confident": True, "label": "soutenu", "reasoning": "clear",
                                       "cited_evidence_ids": ["c1"]})
        client = FakeLLMClient(responses=[filter_response])
        verdict = verify_claim(client, "m1", "m2", "m3", "claim-1", "claim text", [make_chunk()])
        self.assertEqual(verdict.label, "soutenu")
        self.assertEqual(len(client.calls), 1)  # only the pre-debate filter, no debate/judge calls

    def test_uncertain_filter_triggers_debate_and_judge(self):
        filter_response = json.dumps({"confident": False, "label": None, "reasoning": "ambiguous", "cited_evidence_ids": []})
        affirmateur_response = json.dumps([{"text": "supports it", "stance": "support", "cited_evidence_ids": ["c1"], "rebuts": []}])
        sceptique_response = json.dumps([{"text": "undermines it", "stance": "attack", "cited_evidence_ids": ["c1"], "rebuts": []}])
        judge_response = json.dumps({"label": "soutenu_faible", "confidence": 0.5, "reasoning": "r", "cited_claim_ids": []})
        client = FakeLLMClient(responses=[filter_response, affirmateur_response, sceptique_response, judge_response, judge_response])
        verdict = verify_claim(client, "m1", "m2", "m3", "claim-1", "claim text", [make_chunk()])
        self.assertEqual(verdict.label, "soutenu_faible")
        self.assertEqual(len(client.calls), 5)  # filter + affirmateur + sceptique + 2 judge passes

    def test_evidence_hashes_recorded_on_verdict(self):
        filter_response = json.dumps({"confident": True, "label": "contredit", "reasoning": "r", "cited_evidence_ids": ["c1"]})
        client = FakeLLMClient(responses=[filter_response])
        verdict = verify_claim(client, "m1", "m2", "m3", "claim-1", "claim text", [make_chunk(content_hash="abc123")])
        self.assertEqual(verdict.evidence_hashes, {"c1": "abc123"})


class TestAggregateChunk(unittest.TestCase):
    def _verdict(self, label):
        return ClaimVerdict(claim_id="x", label=label, confidence=1.0, reasoning="")

    def test_any_contradiction_rejects_chunk(self):
        self.assertEqual(aggregate_chunk([self._verdict("soutenu"), self._verdict("contredit")]), "rejeté")

    def test_any_inverifiable_without_contradiction_routes_to_human(self):
        self.assertEqual(aggregate_chunk([self._verdict("soutenu"), self._verdict("invérifiable")]), "à vérifier humainement")

    def test_all_supported_is_accepted(self):
        self.assertEqual(aggregate_chunk([self._verdict("soutenu"), self._verdict("soutenu_faible")]), "accepté")

    def test_empty_list_is_accepted_vacuously(self):
        self.assertEqual(aggregate_chunk([]), "accepté")


class TestClaimVerdictSerialization(unittest.TestCase):
    def test_round_trip(self):
        verdict = ClaimVerdict(claim_id="c1", label="soutenu", confidence=0.9, reasoning="r",
                                cited_evidence_ids=("e1",), evidence_hashes={"e1": "hash1"})
        restored = ClaimVerdict.from_dict(verdict.to_dict())
        self.assertEqual(verdict, restored)


if __name__ == "__main__":
    unittest.main()
