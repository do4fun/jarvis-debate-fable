import tempfile
import unittest
from pathlib import Path

from proto.acquire import formulate_anchor_query, search_and_archive, validate_sources
from proto.argument_graph import Evidence, EvidenceLevel
from proto.llm_client import FakeLLMClient


def fake_search_fn(query, base_url):
    return [
        {"url": "https://trusted.example/a", "domain": "trusted.example"},
        {"url": "https://random-blog.example/b", "domain": "random-blog.example"},
    ]


def fake_extract_fn(url):
    return {
        "raw": f"<html>{url}</html>",
        "text": "Title paragraph.\n\nFirst relevant paragraph.\n\nSecond paragraph.\n\nThird paragraph.\n\nFourth (should be excluded).",
        "title": "A Title",
        "published_date": None,
    }


class TestFormulateAnchorQuery(unittest.TestCase):
    def test_single_llm_call_returns_stripped_query(self):
        client = FakeLLMClient(responses=["  best query  "])
        query = formulate_anchor_query(client, "model", "Is X true?")
        self.assertEqual(query, "best query")
        self.assertEqual(len(client.calls), 1)


class TestSearchAndArchive(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.corpus_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_whitelisted_domain_gets_n1_others_fallback_to_n3(self):
        evidence = search_and_archive(
            "query",
            whitelist_n1=("trusted.example",),
            corpus_raw_dir=self.corpus_dir,
            search_fn=fake_search_fn,
            extract_fn=fake_extract_fn,
        )
        self.assertEqual(len(evidence), 2)
        by_url = {e.source_url: e for e in evidence}
        self.assertEqual(by_url["https://trusted.example/a"].level, EvidenceLevel.N1)
        self.assertEqual(by_url["https://random-blog.example/b"].level, EvidenceLevel.N3)

    def test_full_page_archived_but_only_sample_in_excerpt(self):
        evidence = search_and_archive(
            "query", corpus_raw_dir=self.corpus_dir, search_fn=fake_search_fn, extract_fn=fake_extract_fn
        )
        archived_files = list(self.corpus_dir.glob("*.html"))
        self.assertEqual(len(archived_files), 2)
        # full page text (with "Fourth (should be excluded)") is archived...
        self.assertTrue(any("html" in f.read_text(encoding="utf-8") for f in archived_files))
        # ...but never sampled into the excerpt sent to an LLM
        for e in evidence:
            self.assertNotIn("Fourth (should be excluded)", e.excerpt)
            self.assertIn("First relevant paragraph.", e.excerpt)

    def test_limit_caps_number_of_sources(self):
        evidence = search_and_archive(
            "query", limit=1, corpus_raw_dir=self.corpus_dir, search_fn=fake_search_fn, extract_fn=fake_extract_fn
        )
        self.assertEqual(len(evidence), 1)


class TestValidateSources(unittest.TestCase):
    def test_keeps_only_ids_returned_by_llm(self):
        candidates = [
            Evidence(id="src-1", source_url="u1", level=EvidenceLevel.N1, excerpt="a"),
            Evidence(id="src-2", source_url="u2", level=EvidenceLevel.N3, excerpt="b"),
        ]
        client = FakeLLMClient(responses=['["src-1"]'])
        kept = validate_sources(client, "model", "Q", candidates)
        self.assertEqual([e.id for e in kept], ["src-1"])

    def test_empty_candidates_short_circuits_without_llm_call(self):
        client = FakeLLMClient(responses=["should not be consumed"])
        kept = validate_sources(client, "model", "Q", [])
        self.assertEqual(kept, [])
        self.assertEqual(len(client.calls), 0)


if __name__ == "__main__":
    unittest.main()
