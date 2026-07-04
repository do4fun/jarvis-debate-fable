"""Consensus and credibility scoring (v4, features 6-8): S(o), C(a_i), and
persistent trust_weight via EMA.

Defaults below mirror `DECISION.md` (proposed, not yet validated -- point
ouvert n°9 of `plan-implantation-debat-multi-agent-v4.md`). Changing a
validated value means updating both files.

The judge's verdict is never replaced by these scores -- they are input
signals only (v4 invariant): "S(o), C(a_i) et le graphe sont des entrées du
juge ; ils ne remplacent pas son verdict".
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from proto.argument_graph import Claim, Evidence, EvidenceLevel

DEFAULT_LEVEL_WEIGHTS: dict[EvidenceLevel, float] = {
    EvidenceLevel.N1: 1.0,
    EvidenceLevel.N2: 0.6,
    EvidenceLevel.N3: 0.3,
}
DEFAULT_FRESHNESS_HALF_LIFE_DAYS = 730  # ~2 years, DECISION.md (proposed)
DEFAULT_TRUST_WEIGHT = 0.5
DEFAULT_EMA_ALPHA = 0.1
DEFAULT_THETA = 0.6

DEFAULT_TRUST_WEIGHTS_PATH = Path("results/trust_weights.json")


def freshness_decay(published: date | None, as_of: date, half_life_days: int = DEFAULT_FRESHNESS_HALF_LIFE_DAYS) -> float:
    """Exponential decay by age. Undated evidence returns 1.0 -- freshness is
    a distinct axis from level, and an unknown date is not a penalty by
    itself (claims post-cutoff are handled by routing them to evidence-only
    evaluation upstream, not by this function)."""
    if published is None:
        return 1.0
    age_days = max((as_of - published).days, 0)
    return 0.5 ** (age_days / half_life_days)


def evidence_credibility(
    evidence: Evidence,
    as_of: date,
    level_weights: Mapping[EvidenceLevel, float] | None = None,
    half_life_days: int = DEFAULT_FRESHNESS_HALF_LIFE_DAYS,
) -> float:
    weights = level_weights or DEFAULT_LEVEL_WEIGHTS
    return weights[evidence.level] * freshness_decay(evidence.published_date, as_of, half_life_days)


def argument_credibility(
    claim: Claim,
    evidence_by_id: Mapping[str, Evidence],
    as_of: date,
    **kwargs: object,
) -> float:
    """C(a_i) (v4 §3.3.5): mean credibility of the evidence a claim cites.
    A claim citing no evidence gets C=0.0 -- distinct from the judge's
    'invérifiable' label, which is a verdict outcome, not a credibility
    score."""
    cited = [evidence_by_id[eid] for eid in claim.cited_evidence_ids if eid in evidence_by_id]
    if not cited:
        return 0.0
    return sum(evidence_credibility(e, as_of, **kwargs) for e in cited) / len(cited)  # type: ignore[arg-type]


def consensus_score(stances: Mapping[str, float], trust_weights: Mapping[str, float]) -> float:
    """S(o) = sum(trust_weight_i * v_i(o)) / sum(trust_weight_i).

    Normalized by total weight so S(o) stays in the same [0,1] range as
    each v_i(o) regardless of how many agents contributed or the trust_weight
    scale -- comparable against theta either way.
    """
    total_weight = sum(trust_weights.get(agent_id, DEFAULT_TRUST_WEIGHT) for agent_id in stances)
    if total_weight == 0:
        return 0.0
    weighted_sum = sum(trust_weights.get(agent_id, DEFAULT_TRUST_WEIGHT) * v for agent_id, v in stances.items())
    return weighted_sum / total_weight


def meets_consensus(stances: Mapping[str, float], trust_weights: Mapping[str, float], theta: float = DEFAULT_THETA) -> bool:
    return consensus_score(stances, trust_weights) >= theta


@dataclass
class TrustWeightStore:
    """Persistent per-agent trust_weight (v4 feature 7), updated by EMA on
    ground-truth-only outcomes.

    Anti-sycophancy guard (v4 explicit): `update_on_ground_truth` must only be
    called when the claim/verdict has a KNOWN ground truth label (e.g. from a
    test dataset). Never call it from mere inter-agent agreement -- doing so
    would create a reinforcement loop rewarding agreement itself rather than
    correctness. Never injected into prompts: pure harness-side weighting.
    """

    path: Path = DEFAULT_TRUST_WEIGHTS_PATH
    alpha: float = DEFAULT_EMA_ALPHA
    initial_weight: float = DEFAULT_TRUST_WEIGHT

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"alpha": self.alpha, "initial_weight": self.initial_weight, "weights": {}}

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, agent_id: str) -> float:
        data = self._load()
        return data["weights"].get(agent_id, data.get("initial_weight", self.initial_weight))

    def all_weights(self) -> dict[str, float]:
        data = self._load()
        return dict(data["weights"])

    def update_on_ground_truth(self, agent_id: str, was_correct: bool) -> float:
        data = self._load()
        prev = data["weights"].get(agent_id, data.get("initial_weight", self.initial_weight))
        reward = 1.0 if was_correct else 0.0
        alpha = data.get("alpha", self.alpha)
        new_weight = alpha * reward + (1 - alpha) * prev
        data["weights"][agent_id] = new_weight
        self._save(data)
        return new_weight
