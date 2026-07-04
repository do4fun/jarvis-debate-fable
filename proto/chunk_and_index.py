"""Semantic-ish chunking, per-chunk metadata, and a local BM25 index
(v3, 0.6.2-0.6.4). No external dependency: BM25 is implemented in-repo --
the plan calls for "zéro dépendance lourde", embeddings only if BM25 is
measured to plateau."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date
from typing import Sequence

from proto.argument_graph import EvidenceLevel

TARGET_MIN_TOKENS = 200
TARGET_MAX_TOKENS = 400


def _word_count(text: str) -> int:
    return len(text.split())


def chunk_text(text: str, target_min: int = TARGET_MIN_TOKENS, target_max: int = TARGET_MAX_TOKENS) -> list[str]:
    """Split on paragraph boundaries first (the semantic unit), then greedily
    pack paragraphs into chunks within [target_min, target_max] words --
    never a fixed-size cut mid-paragraph. A single paragraph longer than
    target_max is kept whole rather than cut mid-sentence."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for para in paragraphs:
        para_len = _word_count(para)
        if current and current_len + para_len > target_max:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
        current.append(para)
        current_len += para_len
        if current_len >= target_min:
            chunks.append("\n\n".join(current))
            current, current_len = [], 0
    if current:
        chunks.append("\n\n".join(current))
    return chunks


@dataclass
class ChunkMetadata:
    chunk_id: str
    source_url: str
    domain: str
    language: str
    level: EvidenceLevel
    text: str
    published_date: date | None = None
    captured_date: date | None = None


def build_chunks(
    text: str,
    source_url: str,
    domain: str,
    language: str,
    level: EvidenceLevel,
    published_date: date | None = None,
    captured_date: date | None = None,
    id_prefix: str = "chunk",
) -> list[ChunkMetadata]:
    return [
        ChunkMetadata(
            chunk_id=f"{id_prefix}-{i}",
            source_url=source_url,
            domain=domain,
            language=language,
            level=level,
            text=piece,
            published_date=published_date,
            captured_date=captured_date,
        )
        for i, piece in enumerate(chunk_text(text), start=1)
    ]


class BM25Index:
    """Minimal BM25 (Okapi) implementation over a fixed set of chunks."""

    def __init__(self, chunks: Sequence[ChunkMetadata], k1: float = 1.5, b: float = 0.75) -> None:
        self.chunks = list(chunks)
        self.k1 = k1
        self.b = b
        self._tokenized = [self._tokenize(c.text) for c in self.chunks]
        self._doc_len = [len(toks) for toks in self._tokenized]
        self._avgdl = (sum(self._doc_len) / len(self._doc_len)) if self._doc_len else 0.0
        self._df: dict[str, int] = {}
        for toks in self._tokenized:
            for term in set(toks):
                self._df[term] = self._df.get(term, 0) + 1
        self._n = len(self.chunks)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(r"\w+", text.lower())

    def _idf(self, term: str) -> float:
        df = self._df.get(term, 0)
        return math.log((self._n - df + 0.5) / (df + 0.5) + 1)

    def search(self, query: str, top_k: int = 5) -> list[tuple[ChunkMetadata, float]]:
        query_terms = self._tokenize(query)
        scores: list[tuple[ChunkMetadata, float]] = []
        for i, toks in enumerate(self._tokenized):
            tf_counts: dict[str, int] = {}
            for t in toks:
                tf_counts[t] = tf_counts.get(t, 0) + 1
            dl = self._doc_len[i]
            score = 0.0
            for term in query_terms:
                tf = tf_counts.get(term, 0)
                if tf == 0:
                    continue
                idf = self._idf(term)
                denom = tf + self.k1 * (1 - self.b + self.b * dl / (self._avgdl or 1))
                score += idf * (tf * (self.k1 + 1)) / (denom or 1)
            scores.append((self.chunks[i], score))
        scores.sort(key=lambda pair: pair[1], reverse=True)
        return [pair for pair in scores if pair[1] > 0][:top_k]
