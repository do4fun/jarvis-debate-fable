import unittest

from proto.argument_graph import EvidenceLevel
from proto.chunk_and_index import BM25Index, build_chunks
from proto.evidence_match import match_evidence


class TestEvidenceMatch(unittest.TestCase):
    def setUp(self):
        text_a = "The license is MIT and permits redistribution.\n\nContact the maintainers for support."
        text_b = "Benchmarks show the model runs on CPU with acceptable latency.\n\nMemory usage stays under 4GB."
        chunks = build_chunks(text_a, "https://a.example", "a.example", "en", EvidenceLevel.N1, id_prefix="a")
        chunks += build_chunks(text_b, "https://b.example", "b.example", "en", EvidenceLevel.N2, id_prefix="b")
        self.index = BM25Index(chunks)

    def test_matches_evidence_relevant_to_claim(self):
        results = match_evidence(self.index, "What license does the project use?", top_k=1)
        self.assertEqual(len(results), 1)
        self.assertIn("MIT", results[0].text)

    def test_top_k_limits_results(self):
        results = match_evidence(self.index, "license CPU memory benchmark", top_k=1)
        self.assertEqual(len(results), 1)

    def test_no_model_call_involved(self):
        # match_evidence takes no llm_client parameter at all -- purely BM25 (v3, 0.6.5)
        import inspect
        sig = inspect.signature(match_evidence)
        self.assertNotIn("llm_client", sig.parameters)


if __name__ == "__main__":
    unittest.main()
