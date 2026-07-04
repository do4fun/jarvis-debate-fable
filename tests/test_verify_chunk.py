import json
import tempfile
import unittest
from pathlib import Path

from proto.argument_graph import EvidenceLevel
from proto.checkpoint import CheckpointStore
from proto.chunk_and_index import BM25Index, build_chunks
from proto.fact_verification import verify_chunk
from proto.llm_client import FakeLLMClient
from proto.scoring import TrustWeightStore


def make_index():
    chunks = build_chunks(
        "Python is great for scripting.\n\nBM25 ranks documents by term relevance.",
        source_url="https://example.org", domain="example.org", language="en",
        level=EvidenceLevel.N1, content_hash="hashA", id_prefix="c",
    )
    return BM25Index(chunks)


class TestVerifyChunk(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.checkpoints = CheckpointStore(sessions_dir=Path(self.tmpdir.name) / "sessions")
        self.trust_weights = TrustWeightStore(path=Path(self.tmpdir.name) / "trust_weights.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_full_run_decomposes_verifies_each_claim_and_aggregates(self):
        responses = [
            json.dumps(["Python is great for scripting", "BM25 ranks documents"]),  # decompose
            json.dumps({"confident": True, "label": "soutenu", "reasoning": "clear match", "cited_evidence_ids": ["c-1"]}),
            json.dumps({"confident": False, "label": None, "reasoning": "ambiguous", "cited_evidence_ids": []}),
            json.dumps([{"text": "supports", "stance": "support", "cited_evidence_ids": ["c-2"], "rebuts": []}]),
            json.dumps([{"text": "doubts", "stance": "attack", "cited_evidence_ids": ["c-2"], "rebuts": []}]),
            json.dumps({"label": "soutenu_faible", "confidence": 0.5, "reasoning": "r", "cited_claim_ids": []}),
            json.dumps({"label": "soutenu_faible", "confidence": 0.5, "reasoning": "r", "cited_claim_ids": []}),
        ]
        client = FakeLLMClient(responses=list(responses))

        verdicts, chunk_label = verify_chunk(
            client, "m-decompose", "m-affirmateur", "m-sceptique", "m-judge",
            "chunk-1", "Python is great for scripting.\n\nBM25 ranks documents by term relevance.",
            make_index(), checkpoint_store=self.checkpoints, trust_weight_store=self.trust_weights,
        )

        self.assertEqual(len(verdicts), 2)
        self.assertEqual(verdicts[0].label, "soutenu")
        self.assertEqual(verdicts[1].label, "soutenu_faible")
        self.assertEqual(chunk_label, "accepté")
        self.assertEqual(len(client.calls), 7)
        self.assertFalse(self.checkpoints.exists("chunk-1"))  # cleared on completion

    def test_resume_skips_decomposition_and_already_verified_claims(self):
        pre_state = {
            "claims": ["Python is great for scripting", "BM25 ranks documents"],
            "claim_1": {
                "claim_id": "chunk-1-claim-1", "label": "soutenu", "confidence": 1.0,
                "reasoning": "clear", "cited_evidence_ids": ["c-1"], "evidence_hashes": {"c-1": "hashA"},
            },
        }
        self.checkpoints.save("chunk-1", "claim_1", pre_state)

        responses = [
            json.dumps({"confident": False, "label": None, "reasoning": "ambiguous", "cited_evidence_ids": []}),
            json.dumps([{"text": "supports", "stance": "support", "cited_evidence_ids": ["c-2"], "rebuts": []}]),
            json.dumps([{"text": "doubts", "stance": "attack", "cited_evidence_ids": ["c-2"], "rebuts": []}]),
            json.dumps({"label": "contredit", "confidence": 0.7, "reasoning": "r", "cited_claim_ids": []}),
            json.dumps({"label": "contredit", "confidence": 0.7, "reasoning": "r", "cited_claim_ids": []}),
        ]
        client = FakeLLMClient(responses=list(responses))

        verdicts, chunk_label = verify_chunk(
            client, "m-decompose", "m-affirmateur", "m-sceptique", "m-judge",
            "chunk-1", "Python is great for scripting.\n\nBM25 ranks documents by term relevance.",
            make_index(), checkpoint_store=self.checkpoints, trust_weight_store=self.trust_weights,
        )

        self.assertEqual(len(client.calls), 5)  # no decompose call, no re-verification of claim 1
        self.assertEqual(verdicts[0].label, "soutenu")  # restored from checkpoint
        self.assertEqual(verdicts[1].label, "contredit")
        self.assertEqual(chunk_label, "rejeté")  # any "contredit" rejects the chunk

    def test_evidence_hashes_flow_through_to_verdicts(self):
        # Both paragraphs are far shorter than chunk_text()'s target_min (200
        # words), so build_chunks() merges them into a single chunk "c-1" --
        # both claims retrieve evidence from that one chunk. This test
        # verifies the hash propagates from retrieval to the verdict, not
        # that retrieval picks distinct chunks per claim (see
        # test_chunk_and_index.py for chunking-size behavior).
        responses = [
            json.dumps(["Python is great for scripting", "BM25 ranks documents"]),
            json.dumps({"confident": True, "label": "soutenu", "reasoning": "r", "cited_evidence_ids": ["c-1"]}),
            json.dumps({"confident": True, "label": "contredit", "reasoning": "r", "cited_evidence_ids": ["c-1"]}),
        ]
        client = FakeLLMClient(responses=responses)
        verdicts, _ = verify_chunk(
            client, "m1", "m2", "m3", "m4", "chunk-1",
            "Python is great for scripting.\n\nBM25 ranks documents by term relevance.",
            make_index(), checkpoint_store=self.checkpoints, trust_weight_store=self.trust_weights,
        )
        self.assertEqual(verdicts[0].evidence_hashes, {"c-1": "hashA"})
        self.assertEqual(verdicts[1].evidence_hashes, {"c-1": "hashA"})


if __name__ == "__main__":
    unittest.main()
