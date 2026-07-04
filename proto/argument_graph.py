"""Argument graph: claims, evidence, support/attack relations, and mechanical
(non-LLM) conflict detection (v4, feature 5; pipeline steps [5]-[6]).

The graph is the canonical representation of a debate (v4): the structured
inter-turn summary (v3 correction F5) is a text projection of it, not the
other way around.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class EvidenceLevel(str, Enum):
    N1 = "N1"
    N2 = "N2"
    N3 = "N3"


class Stance(str, Enum):
    SUPPORT = "support"
    ATTACK = "attack"


class RelationType(str, Enum):
    SUPPORT = "support"
    ATTACK = "attack"


@dataclass(frozen=True)
class Evidence:
    id: str
    source_url: str
    level: EvidenceLevel
    excerpt: str
    published_date: date | None = None
    captured_date: date | None = None
    content_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_url": self.source_url,
            "level": self.level.value,
            "excerpt": self.excerpt,
            "published_date": self.published_date.isoformat() if self.published_date else None,
            "captured_date": self.captured_date.isoformat() if self.captured_date else None,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Evidence":
        return cls(
            id=data["id"],
            source_url=data["source_url"],
            level=EvidenceLevel(data["level"]),
            excerpt=data["excerpt"],
            published_date=date.fromisoformat(data["published_date"]) if data.get("published_date") else None,
            captured_date=date.fromisoformat(data["captured_date"]) if data.get("captured_date") else None,
            content_hash=data.get("content_hash"),
        )


@dataclass
class Claim:
    id: str
    author_role: str  # "advocate" | "challenger"
    text: str
    stance: Stance
    cited_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    rebuts: tuple[str, ...] = field(default_factory=tuple)  # explicit claim IDs this claim counters

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "author_role": self.author_role,
            "text": self.text,
            "stance": self.stance.value,
            "cited_evidence_ids": list(self.cited_evidence_ids),
            "rebuts": list(self.rebuts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Claim":
        return cls(
            id=data["id"],
            author_role=data["author_role"],
            text=data["text"],
            stance=Stance(data["stance"]),
            cited_evidence_ids=tuple(data.get("cited_evidence_ids", [])),
            rebuts=tuple(data.get("rebuts", [])),
        )


@dataclass(frozen=True)
class Relation:
    type: RelationType
    source_claim_id: str
    target_claim_id: str
    reason: str  # "explicit_rebuttal" | "shared_evidence_opposing_stance"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "source_claim_id": self.source_claim_id,
            "target_claim_id": self.target_claim_id,
            "reason": self.reason,
        }


class ArgumentGraph:
    """Claims and Evidence as nodes, support/attack Relations as edges."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._evidence: dict[str, Evidence] = {}
        self._relations: list[Relation] = []

    def add_claim(self, claim: Claim) -> None:
        if claim.id in self._claims:
            raise ValueError(f"duplicate claim id: {claim.id}")
        self._claims[claim.id] = claim

    def add_evidence(self, evidence: Evidence) -> None:
        if evidence.id in self._evidence:
            raise ValueError(f"duplicate evidence id: {evidence.id}")
        self._evidence[evidence.id] = evidence

    def add_relation(self, relation: Relation) -> None:
        self._relations.append(relation)

    @property
    def claims(self) -> tuple[Claim, ...]:
        return tuple(self._claims.values())

    @property
    def evidence(self) -> tuple[Evidence, ...]:
        return tuple(self._evidence.values())

    @property
    def relations(self) -> tuple[Relation, ...]:
        return tuple(self._relations)

    def claim(self, claim_id: str) -> Claim:
        return self._claims[claim_id]

    def evidence_for(self, claim_id: str) -> tuple[Evidence, ...]:
        cited = self._claims[claim_id].cited_evidence_ids
        return tuple(self._evidence[eid] for eid in cited if eid in self._evidence)

    def detect_conflicts(self) -> list[Relation]:
        """Mechanical (non-LLM) extraction of claim/counter-claim pairs,
        derived purely from ID citations (v4 feature 5, pipeline step [5]):

        1. Explicit rebuttal: a claim declares `rebuts=(other_claim_id,)`.
        2. Shared evidence, opposing stance: two claims from different
           author_roles cite the same evidence id but declare opposite
           stances -- a conflict surfaces from the citation graph alone,
           without a judge call.

        Idempotent: relations already added by a previous call are not
        duplicated (checked by identical (type, source, target, reason)).
        """
        found: list[Relation] = []
        claims = list(self._claims.values())

        for claim in claims:
            for target_id in claim.rebuts:
                if target_id in self._claims:
                    found.append(Relation(RelationType.ATTACK, claim.id, target_id, "explicit_rebuttal"))

        for i, c1 in enumerate(claims):
            for c2 in claims[i + 1:]:
                if c1.author_role == c2.author_role:
                    continue
                shared = set(c1.cited_evidence_ids) & set(c2.cited_evidence_ids)
                if shared and c1.stance != c2.stance:
                    found.append(Relation(RelationType.ATTACK, c1.id, c2.id, "shared_evidence_opposing_stance"))

        existing = set(self._relations)
        new_relations = [r for r in found if r not in existing]
        for relation in new_relations:
            self.add_relation(relation)
        return new_relations

    def to_dict(self) -> dict[str, Any]:
        return {
            "claims": [c.to_dict() for c in self.claims],
            "evidence": [e.to_dict() for e in self.evidence],
            "relations": [r.to_dict() for r in self.relations],
        }
