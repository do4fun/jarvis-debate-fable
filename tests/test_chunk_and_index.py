import unittest
from datetime import date

from proto.argument_graph import EvidenceLevel
from proto.chunk_and_index import BM25Index, build_chunks, chunk_text


class TestChunkText(unittest.TestCase):
    def test_short_text_is_a_single_chunk(self):
        text = "Paragraph one.\n\nParagraph two."
        self.assertEqual(chunk_text(text), [text])

    def test_never_splits_a_paragraph_mid_sentence(self):
        long_paragraph = " ".join(["word"] * 500)
        chunks = chunk_text(long_paragraph)
        # a single paragraph longer than target_max is kept whole, not cut
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], long_paragraph)

    def test_packs_paragraphs_up_to_target_max(self):
        paragraphs = ["word " * 100 for _ in range(5)]  # 100 words each, 5 paragraphs = 500 words
        text = "\n\n".join(paragraphs)
        chunks = chunk_text(text, target_min=200, target_max=400)
        for chunk in chunks[:-1]:
            word_count = len(chunk.split())
            self.assertGreaterEqual(word_count, 200)
            self.assertLessEqual(word_count, 400)

    def test_empty_text_yields_no_chunks(self):
        self.assertEqual(chunk_text(""), [])


class TestBuildChunks(unittest.TestCase):
    def test_metadata_attached_to_every_chunk(self):
        chunks = build_chunks(
            "Some paragraph.\n\nAnother paragraph.",
            source_url="https://example.org/a",
            domain="example.org",
            language="en",
            level=EvidenceLevel.N1,
            published_date=date(2024, 1, 1),
            captured_date=date(2024, 1, 2),
        )
        self.assertTrue(chunks)
        for chunk in chunks:
            self.assertEqual(chunk.source_url, "https://example.org/a")
            self.assertEqual(chunk.domain, "example.org")
            self.assertEqual(chunk.level, EvidenceLevel.N1)
            self.assertEqual(chunk.published_date, date(2024, 1, 1))

    def test_chunk_ids_are_unique_and_prefixed(self):
        text = "\n\n".join(["word " * 250] * 3)
        chunks = build_chunks(text, "u", "d", "en", EvidenceLevel.N2, id_prefix="src1")
        ids = [c.chunk_id for c in chunks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(cid.startswith("src1-") for cid in ids))


class TestBM25Index(unittest.TestCase):
    def setUp(self):
        self.chunks = build_chunks(
            "Python is a programming language.\n\nBM25 is a ranking function used by search engines.",
            source_url="u", domain="d", language="en", level=EvidenceLevel.N1,
        )
        self.index = BM25Index(self.chunks)

    def test_search_returns_relevant_chunk_first(self):
        results = self.index.search("BM25 ranking search engines", top_k=2)
        self.assertTrue(results)
        self.assertIn("BM25", results[0][0].text)

    def test_search_with_no_matching_terms_returns_empty(self):
        results = self.index.search("completely unrelated query zzz", top_k=5)
        self.assertEqual(results, [])

    def test_empty_index_returns_empty(self):
        empty_index = BM25Index([])
        self.assertEqual(empty_index.search("anything"), [])


if __name__ == "__main__":
    unittest.main()
