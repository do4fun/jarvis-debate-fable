"""Persistent claim verdicts, keyed by the evidence hash they depended on
(v3 correction Axe 2.4, v4 traceability table item 2.4): if a later re-crawl
changes the hash of evidence a verdict cited, that verdict is automatically
invalidated and the claim is queued for re-verification -- a verdict is only
as fresh as the evidence it was built on.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from proto.fact_verification import ClaimVerdict

DEFAULT_VERDICTS_PATH = Path("results/verdicts.json")


@dataclass
class VerdictStore:
    path: Path = DEFAULT_VERDICTS_PATH

    def _load(self) -> dict[str, dict]:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {}

    def _save(self, data: dict[str, dict]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save(self, verdict: ClaimVerdict) -> None:
        data = self._load()
        data[verdict.claim_id] = verdict.to_dict()
        self._save(data)

    def get(self, claim_id: str) -> ClaimVerdict | None:
        data = self._load()
        if claim_id not in data:
            return None
        return ClaimVerdict.from_dict(data[claim_id])

    def all_claim_ids(self) -> list[str]:
        return list(self._load().keys())

    def invalidate_stale(self, current_hashes: Mapping[str, str]) -> list[str]:
        """`current_hashes`: evidence_id -> hash as of a fresh crawl. Any
        stored verdict that cited an evidence_id whose hash changed (or that
        no longer appears in `current_hashes`) is deleted; its claim_id is
        returned so the caller can re-queue it for verification (2.1).
        Verdicts that cited no hashed evidence at all (e.g. "invérifiable"
        with no evidence) are never invalidated by this mechanism."""
        data = self._load()
        stale: list[str] = []
        for claim_id, verdict_data in list(data.items()):
            evidence_hashes = verdict_data.get("evidence_hashes", {})
            if not evidence_hashes:
                continue
            for evidence_id, stored_hash in evidence_hashes.items():
                current_hash = current_hashes.get(evidence_id)
                if current_hash != stored_hash:
                    stale.append(claim_id)
                    del data[claim_id]
                    break
        if stale:
            self._save(data)
        return stale
