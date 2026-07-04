"""Pipeline step [1]: single-anchor web research, closed before any debate
(v4 feature 2, spec in `docs/PLAN_recherche_web.md`).

Real network calls (SearXNG + trafilatura) are lazy-imported so this module
-- and everything that imports it -- stays importable and unit-testable
without those services installed or reachable. `search_fn`/`extract_fn` are
injection points for tests.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Callable, Sequence

from proto.argument_graph import Evidence, EvidenceLevel
from proto.llm_client import LLMClient

DEFAULT_CORPUS_RAW_DIR = Path("corpus/raw")

ANCHOR_QUERY_SYSTEM_PROMPT = (
    "Formulate a single, short web search query (suitable for a search "
    "engine) that best anchors research for the debate question below. "
    "Respond with the query text only, no explanation."
)

VALIDATION_SYSTEM_PROMPT = (
    "You validate candidate sources before they enter a debate's fact sheet. "
    "For each source, check relevance to the question, metadata coherence "
    "(date, domain), and confidence level. Respond ONLY with JSON: a list of "
    'the source IDs to KEEP, e.g. ["src-1", "src-3"].'
)


def formulate_anchor_query(llm_client: LLMClient, model: str, question: str) -> str:
    """1 LLM call, once per debate (v4 feature 2: 2 calls total for the whole
    research phase regardless of downstream agents/iterations)."""
    return llm_client.complete(question, model=model, system=ANCHOR_QUERY_SYSTEM_PROMPT).strip()


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def search_and_archive(
    query: str,
    *,
    searxng_base_url: str = "http://localhost:8080",
    whitelist_n1: Sequence[str] = (),
    whitelist_n2: Sequence[str] = (),
    limit: int = 5,
    corpus_raw_dir: Path = DEFAULT_CORPUS_RAW_DIR,
    search_fn: Callable[[str, str], list[dict]] | None = None,
    extract_fn: Callable[[str], dict] | None = None,
) -> list[Evidence]:
    """Search once, archive full pages to `corpus_raw_dir` (hash + capture
    date, for hash-based invalidation on re-crawl), and sample only
    title + first 3 paragraphs into the returned Evidence -- the full page
    never enters an LLM prompt (v4 guard). Domains outside the N1/N2
    whitelist are admitted only as an explicit N3 fallback.
    """
    search_fn = search_fn or _searxng_search
    extract_fn = extract_fn or _trafilatura_extract

    results = search_fn(query, searxng_base_url)
    corpus_raw_dir.mkdir(parents=True, exist_ok=True)
    evidence: list[Evidence] = []
    for i, result in enumerate(results[:limit], start=1):
        url = result["url"]
        domain = result.get("domain") or url.split("/")[2]
        extracted = extract_fn(url)
        raw_html = extracted.get("raw", "")
        content_hash = _sha256(raw_html.encode("utf-8"))
        (corpus_raw_dir / f"{content_hash}.html").write_text(raw_html, encoding="utf-8")

        if domain in whitelist_n1:
            level = EvidenceLevel.N1
        elif domain in whitelist_n2:
            level = EvidenceLevel.N2
        else:
            level = EvidenceLevel.N3  # explicit fallback, marked by the level itself

        paragraphs = [p for p in extracted.get("text", "").split("\n\n") if p.strip()]
        sample = "\n\n".join(([extracted.get("title", "")] if extracted.get("title") else []) + paragraphs[:3])

        evidence.append(
            Evidence(
                id=f"src-{i}",
                source_url=url,
                level=level,
                excerpt=sample,
                published_date=extracted.get("published_date"),
                captured_date=date.today(),
                content_hash=content_hash,
            )
        )
    return evidence


def _searxng_search(query: str, base_url: str) -> list[dict]:
    import requests  # lazy import -- only needed for real execution

    response = requests.get(f"{base_url.rstrip('/')}/search", params={"q": query, "format": "json"}, timeout=30)
    response.raise_for_status()
    data = response.json()
    return [{"url": r["url"], "domain": (r.get("parsed_url") or [None, None])[1]} for r in data.get("results", [])]


def _trafilatura_extract(url: str) -> dict:
    import requests  # lazy import
    import trafilatura  # lazy import -- optional dependency, only for real execution

    raw_html = requests.get(url, timeout=30).text
    text = trafilatura.extract(raw_html) or ""
    metadata = trafilatura.extract_metadata(raw_html)
    return {
        "raw": raw_html,
        "text": text,
        "title": getattr(metadata, "title", "") or "",
        "published_date": getattr(metadata, "date", None),
    }


def validate_sources(llm_client: LLMClient, model: str, question: str, candidates: Sequence[Evidence]) -> list[Evidence]:
    """1 LLM call: validate relevance/metadata/confidence before injection
    into the fact sheet (shared role with the pre-debate filter F4, not an
    extra agent)."""
    if not candidates:
        return []
    listing = "\n".join(f"[{e.id}] ({e.level.value}, {e.source_url}): {e.excerpt[:200]}" for e in candidates)
    prompt = f"Question: {question}\n\nCandidate sources:\n{listing}"
    raw = llm_client.complete(prompt, model=model, system=VALIDATION_SYSTEM_PROMPT)
    kept_ids = set(json.loads(raw))
    return [e for e in candidates if e.id in kept_ids]
