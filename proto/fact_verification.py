"""MAD-Fact: the fact-verification pipeline (v3 Phase 2, 2.1; v4 additions:
argument graph replaces free-form debate output, checkpoint per claim).

Per claim:
  1. Retrieve evidence locally (BM25, no LLM call -- `proto/evidence_match.py`).
     No evidence at all -> "invérifiable" immediately, no LLM call either.
  2. Pre-debate filter (1 LLM call, correction F4): the judge alone checks the
     claim against the retrieved evidence. If confident, that is the verdict
     -- no debate is triggered. Debate is reserved for claims where the judge
     alone is uncertain (inversion of the v2 plan, which always debated).
  3. Only for uncertain claims: 1-round debate, affirmateur vs sceptique,
     arguing only from the retrieved evidence and its N1/N2/N3 level -- never
     from parametric memory for post-cutoff claims (F1/F2, same guard as
     `proto/debate_local.py`).
  4. Judge, double pass reversed order (F6) -> label + confidence + cited IDs.
     Divergence between passes maps to "invérifiable" (genuine ambiguity,
     same spirit as the pipeline's "indécidable").

Chunk-level aggregation: any "contredit" claim rejects the whole chunk; else
any "invérifiable" claim routes it to human review; else it's accepted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence

from proto import debate_local
from proto.argument_graph import ArgumentGraph, Claim, Evidence
from proto.checkpoint import CheckpointStore
from proto.chunk_and_index import BM25Index, ChunkMetadata
from proto.evidence_match import match_evidence
from proto.llm_client import LLMClient
from proto.scoring import TrustWeightStore, argument_credibility, consensus_score, stances_from_claims

LABELS = ("soutenu", "soutenu_faible", "contredit", "invérifiable")


class FactVerificationError(RuntimeError):
    """Raised when an LLM's structured JSON output doesn't match the
    expected schema."""


DECOMPOSE_SYSTEM_PROMPT = (
    "Decompose the given text chunk into atomic factual claims -- each claim "
    "must be a single, independently checkable statement. Respond ONLY with "
    'JSON: a list of strings, e.g. ["claim one", "claim two"].'
)


def decompose_into_claims(llm_client: LLMClient, model: str, chunk_text: str) -> list[str]:
    """1 LLM call per chunk (not per claim, not per debate turn -- v3
    correction F4)."""
    raw = llm_client.complete(chunk_text, model=model, system=DECOMPOSE_SYSTEM_PROMPT)
    try:
        claims = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FactVerificationError(f"decomposition output is not valid JSON: {raw!r}") from exc
    if not isinstance(claims, list) or not all(isinstance(c, str) for c in claims):
        raise FactVerificationError(f"decomposition output is not a list of strings: {raw!r}")
    return claims


def chunk_to_evidence(chunk: ChunkMetadata) -> Evidence:
    """Bridge from a retrieved corpus chunk (`proto/chunk_and_index.py`) to
    the `Evidence` shape the debate/graph machinery expects."""
    return Evidence(
        id=chunk.chunk_id,
        source_url=chunk.source_url,
        level=chunk.level,
        excerpt=chunk.text,
        published_date=chunk.published_date,
        captured_date=chunk.captured_date,
        content_hash=chunk.content_hash,
    )


@dataclass
class FilterResult:
    confident: bool
    label: str | None
    reasoning: str
    cited_evidence_ids: tuple[str, ...] = field(default_factory=tuple)


PRE_FILTER_SYSTEM_PROMPT = (
    "You are a fact-checking judge doing a quick pre-debate filter (this is "
    "the ONLY judge call for a claim unless the evidence is genuinely "
    "ambiguous). Given a claim and retrieved evidence excerpts (with "
    "N1/N2/N3 confidence levels), decide if the evidence clearly and "
    "unambiguously supports or contradicts the claim. Respond ONLY with "
    'JSON: {"confident": bool, "label": "soutenu"|"soutenu_faible"|'
    '"contredit"|null, "reasoning": str, "cited_evidence_ids": [str]}. Set '
    'confident=true (with a non-null label) only when there is no real '
    "ambiguity; otherwise confident=false, label=null -- this routes the "
    "claim to a 1-round debate instead of guessing. \"soutenu_faible\" is "
    "for support resting solely on N3 (tertiary) evidence."
)


def pre_debate_filter(llm_client: LLMClient, model: str, claim_text: str, evidence: Sequence[ChunkMetadata]) -> FilterResult:
    if not evidence:
        return FilterResult(confident=True, label="invérifiable", reasoning="aucune évidence retrouvée")
    listing = "\n".join(f"[{e.chunk_id}] ({e.level.value}): {e.text[:300]}" for e in evidence)
    prompt = f"Claim: {claim_text}\n\nEvidence:\n{listing}"
    raw = llm_client.complete(prompt, model=model, system=PRE_FILTER_SYSTEM_PROMPT)
    try:
        parsed = json.loads(raw)
        return FilterResult(
            confident=parsed["confident"],
            label=parsed.get("label"),
            reasoning=parsed.get("reasoning", ""),
            cited_evidence_ids=tuple(parsed.get("cited_evidence_ids", [])),
        )
    except (json.JSONDecodeError, KeyError) as exc:
        raise FactVerificationError(f"pre-debate filter output malformed: {raw!r}") from exc


@dataclass
class ClaimJudgePass:
    label: str
    confidence: float
    reasoning: str
    cited_claim_ids: tuple[str, ...]
    order: str  # "affirmateur_first" | "sceptique_first"


CLAIM_JUDGE_SYSTEM_PROMPT = (
    "You are the fact-checking judge for a single claim, second stage (after "
    "a 1-round debate between an affirmer and a skeptic). Weigh arguments by "
    "the credibility of the evidence they cite; the credibility/consensus "
    "scores given below are signals, not a verdict you must follow. Respond "
    'ONLY with JSON: {"label": "soutenu"|"soutenu_faible"|"contredit"|'
    '"invérifiable", "confidence": float (0-1), "reasoning": str, '
    '"cited_claim_ids": [str]}. Use "invérifiable" when the debate leaves '
    "genuine ambiguity."
)


def _run_claim_judge_pass(
    llm_client: LLMClient, model: str, claim_text: str, claims_in_order: Sequence[Claim],
    credibility: dict, consensus: float, order_label: str,
) -> ClaimJudgePass:
    claims_text = "\n".join(
        f"[{c.id}] ({c.author_role}, {c.stance.value}) {c.text} (cites: {', '.join(c.cited_evidence_ids) or 'none'})"
        for c in claims_in_order
    )
    prompt = (
        f"Claim under review: {claim_text}\n\nDebate claims (order: {order_label}):\n{claims_text}\n\n"
        f"Argument credibility C(a_i): {credibility}\nConsensus S(o): {consensus}"
    )
    raw = llm_client.complete(prompt, model=model, system=CLAIM_JUDGE_SYSTEM_PROMPT)
    try:
        parsed = json.loads(raw)
        return ClaimJudgePass(
            label=parsed["label"],
            confidence=float(parsed["confidence"]),
            reasoning=parsed.get("reasoning", ""),
            cited_claim_ids=tuple(parsed.get("cited_claim_ids", [])),
            order=order_label,
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise FactVerificationError(f"claim judge output malformed: {raw!r}") from exc


def double_pass_claim_judge(
    llm_client: LLMClient, model: str, claim_text: str,
    affirmateur_claims: Sequence[Claim], sceptique_claims: Sequence[Claim],
    credibility: dict, consensus: float,
) -> tuple[ClaimJudgePass, ClaimJudgePass, ClaimJudgePass]:
    """Double pass, reversed order (F6). On divergence, the final pass is
    forced to "invérifiable" -- an undecidable claim is handled the same way
    as one with no evidence at all, both routing to human review at the
    chunk-aggregation stage."""
    pass_1 = _run_claim_judge_pass(
        llm_client, model, claim_text, list(affirmateur_claims) + list(sceptique_claims),
        credibility, consensus, "affirmateur_first",
    )
    pass_2 = _run_claim_judge_pass(
        llm_client, model, claim_text, list(sceptique_claims) + list(affirmateur_claims),
        credibility, consensus, "sceptique_first",
    )
    if pass_1.label == pass_2.label:
        reasoning = pass_1.reasoning if pass_1.reasoning == pass_2.reasoning else (
            f"[advocate-first] {pass_1.reasoning} | [sceptique-first] {pass_2.reasoning}"
        )
        final = ClaimJudgePass(
            label=pass_1.label,
            confidence=(pass_1.confidence + pass_2.confidence) / 2,
            reasoning=reasoning,
            cited_claim_ids=tuple(set(pass_1.cited_claim_ids) | set(pass_2.cited_claim_ids)),
            order="final",
        )
    else:
        final = ClaimJudgePass(
            label="invérifiable", confidence=0.0,
            reasoning="divergence inter-passage (F6)", cited_claim_ids=(), order="final",
        )
    return pass_1, pass_2, final


@dataclass
class ClaimVerdict:
    claim_id: str
    label: str
    confidence: float
    reasoning: str
    cited_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence_hashes: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "label": self.label,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "cited_evidence_ids": list(self.cited_evidence_ids),
            "evidence_hashes": dict(self.evidence_hashes),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ClaimVerdict":
        return cls(
            claim_id=data["claim_id"],
            label=data["label"],
            confidence=data["confidence"],
            reasoning=data.get("reasoning", ""),
            cited_evidence_ids=tuple(data.get("cited_evidence_ids", [])),
            evidence_hashes=dict(data.get("evidence_hashes", {})),
        )


def verify_claim(
    llm_client: LLMClient,
    model_affirmateur: str,
    model_sceptique: str,
    model_judge: str,
    claim_id: str,
    claim_text: str,
    chunks: Sequence[ChunkMetadata],
    *,
    as_of: date | None = None,
    trust_weight_store: TrustWeightStore | None = None,
) -> ClaimVerdict:
    as_of = as_of or date.today()

    if not chunks:
        return ClaimVerdict(claim_id=claim_id, label="invérifiable", confidence=1.0, reasoning="aucune évidence retrouvée")

    evidence = [chunk_to_evidence(c) for c in chunks]
    evidence_hashes = {e.id: e.content_hash for e in evidence if e.content_hash}

    filter_result = pre_debate_filter(llm_client, model_judge, claim_text, chunks)
    if filter_result.confident:
        return ClaimVerdict(
            claim_id=claim_id,
            label=filter_result.label or "invérifiable",
            confidence=1.0,
            reasoning=filter_result.reasoning,
            cited_evidence_ids=filter_result.cited_evidence_ids,
            evidence_hashes=evidence_hashes,
        )

    affirmateur_claims = debate_local.generate_position(
        llm_client, model_affirmateur, "affirmateur", claim_text, evidence, "affirmateur"
    )
    sceptique_claims = debate_local.generate_position(
        llm_client, model_sceptique, "sceptique", claim_text, evidence, "sceptique"
    )

    graph = ArgumentGraph()
    for e in evidence:
        graph.add_evidence(e)
    for c in affirmateur_claims + sceptique_claims:
        graph.add_claim(c)
    graph.detect_conflicts()

    evidence_by_id = {e.id: e for e in evidence}
    credibility = {c.id: argument_credibility(c, evidence_by_id, as_of) for c in graph.claims}
    trust_weights = trust_weight_store or TrustWeightStore()
    consensus = consensus_score(stances_from_claims(graph.claims), trust_weights.all_weights())

    _, _, final = double_pass_claim_judge(
        llm_client, model_judge, claim_text, affirmateur_claims, sceptique_claims, credibility, consensus
    )
    return ClaimVerdict(
        claim_id=claim_id,
        label=final.label,
        confidence=final.confidence,
        reasoning=final.reasoning,
        cited_evidence_ids=final.cited_claim_ids,
        evidence_hashes=evidence_hashes,
    )


def aggregate_chunk(claim_verdicts: Sequence[ClaimVerdict]) -> str:
    """Deterministic aggregation rule (prototype default, to validate):
    any contradiction rejects the whole chunk; else any unverifiable claim
    routes it to human review; else it is accepted."""
    labels = {v.label for v in claim_verdicts}
    if "contredit" in labels:
        return "rejeté"
    if "invérifiable" in labels:
        return "à vérifier humainement"
    return "accepté"


def verify_chunk(
    llm_client: LLMClient,
    model_decompose: str,
    model_affirmateur: str,
    model_sceptique: str,
    model_judge: str,
    chunk_id: str,
    chunk_text: str,
    index: BM25Index,
    *,
    top_k: int = 3,
    as_of: date | None = None,
    trust_weight_store: TrustWeightStore | None = None,
    checkpoint_store: CheckpointStore | None = None,
) -> tuple[list[ClaimVerdict], str]:
    """Full 2.1 pipeline for one chunk: decompose into atomic claims, then
    for each claim retrieve local evidence (BM25, no LLM call) and verify it
    -- checkpointed after every claim, so an interrupted run over a large
    corpus resumes at the exact claim rather than re-decomposing or
    re-verifying already-judged claims (0.6/2.1: "checkpoint après chaque
    claim").

    Persistence beyond the checkpoint (e.g. `proto/verdict_store.py`, for
    hash-based invalidation) is the caller's responsibility -- this function
    only computes verdicts, to avoid a dependency cycle between
    fact_verification and verdict_store.
    """
    checkpoints = checkpoint_store or CheckpointStore()
    existing = checkpoints.load(chunk_id)
    state: dict = dict(existing.state) if existing else {}

    if "claims" in state:
        claim_texts: list[str] = state["claims"]
    else:
        claim_texts = decompose_into_claims(llm_client, model_decompose, chunk_text)
        state["claims"] = claim_texts
        checkpoints.save(chunk_id, "decompose", state)

    verdicts: list[ClaimVerdict] = []
    for i, claim_text in enumerate(claim_texts, start=1):
        claim_key = f"claim_{i}"
        if claim_key in state:
            verdicts.append(ClaimVerdict.from_dict(state[claim_key]))
            continue
        retrieved = match_evidence(index, claim_text, top_k=top_k)
        verdict = verify_claim(
            llm_client, model_affirmateur, model_sceptique, model_judge,
            f"{chunk_id}-claim-{i}", claim_text, retrieved,
            as_of=as_of, trust_weight_store=trust_weight_store,
        )
        state[claim_key] = verdict.to_dict()
        checkpoints.save(chunk_id, claim_key, state)
        verdicts.append(verdict)

    chunk_label = aggregate_chunk(verdicts)
    checkpoints.clear(chunk_id)
    return verdicts, chunk_label
