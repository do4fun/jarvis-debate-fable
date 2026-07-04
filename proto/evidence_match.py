"""Retrieve corpus evidence for each atomic claim via BM25 -- no model call
(v3, 0.6.5): "pas d'appel modèle — BM25"."""
from __future__ import annotations

from proto.chunk_and_index import BM25Index, ChunkMetadata


def match_evidence(index: BM25Index, claim_text: str, top_k: int = 3) -> list[ChunkMetadata]:
    return [chunk for chunk, _score in index.search(claim_text, top_k=top_k)]
