"""The 2-debater + judge engine (v3), reused by `proto/pipeline.py` as steps
[3] thesis, [4] antithesis, [7] synthesis.

Debates are stateless on content: no verdict or claim from a previous debate
is ever included in a prompt here (v4 invariant, precision on trust_weight --
the only thing that persists across debates is the harness-side
trust_weight, never a prompt).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from proto.argument_graph import Claim, Evidence, Stance
from proto.llm_client import LLMClient


class DebateParsingError(RuntimeError):
    """Raised when an agent's structured JSON output doesn't match the
    expected schema -- surfaced loudly rather than guessed at, since a
    malformed claim would silently corrupt the argument graph."""


POSITION_SYSTEM_PROMPT = (
    "You are a debate participant in role '{role}'. You are given a question "
    "and a fact sheet made only of evidence excerpts with IDs -- never use "
    "your own parametric memory for claims after the model's knowledge "
    "cutoff; if the fact sheet has no evidence for a point, do not claim it. "
    "Respond ONLY with JSON: a list of claims, each "
    '{{"text": str, "stance": "support"|"attack", "cited_evidence_ids": [str], '
    '"rebuts": [str]}} where "rebuts" lists the IDs of opposing claims this '
    "one directly counters (only when opposing claims are given below; "
    "otherwise [])."
)


def _build_fact_sheet(evidence: Sequence[Evidence]) -> str:
    return "\n".join(f"[{e.id}] ({e.level.value}, {e.source_url}): {e.excerpt}" for e in evidence)


def generate_position(
    llm_client: LLMClient,
    model: str,
    role: str,
    question: str,
    evidence: Sequence[Evidence],
    claim_id_prefix: str,
    opposing_claims: Sequence[Claim] = (),
    brainstorming_notes: str = "",
) -> list[Claim]:
    """One LLM call producing a list of Claims for `role` (advocate/challenger).

    `opposing_claims` should stay empty for round 1 (parallel, no mutual
    visibility by default -- `DebateConfig.speaking_order`); pass the
    structured summary of the other side only for a round-2 rebuttal
    (v3 correction F5: summary, never raw prose).

    `brainstorming_notes` (v4 pipeline step [2]) feeds the options/angles
    enumerated before either debater takes a position -- non-binding, it
    informs the position without fixing it.
    """
    prompt_parts = [f"Question: {question}", "Fact sheet:", _build_fact_sheet(evidence)]
    if brainstorming_notes:
        prompt_parts += ["Brainstorming (options/angles, non-binding):", brainstorming_notes]
    if opposing_claims:
        summary = "\n".join(
            f"[{c.id}] {c.text} (cites: {', '.join(c.cited_evidence_ids) or 'none'})" for c in opposing_claims
        )
        prompt_parts += ["Opposing position (structured summary, round 2 rebuttal target):", summary]
    prompt = "\n\n".join(prompt_parts)
    system = POSITION_SYSTEM_PROMPT.format(role=role)
    raw = llm_client.complete(prompt, model=model, system=system)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DebateParsingError(f"{role} output is not valid JSON: {raw!r}") from exc

    claims: list[Claim] = []
    for i, item in enumerate(parsed, start=1):
        try:
            claims.append(
                Claim(
                    id=f"{claim_id_prefix}-{i}",
                    author_role=role,
                    text=item["text"],
                    stance=Stance(item["stance"]),
                    cited_evidence_ids=tuple(item.get("cited_evidence_ids", [])),
                    rebuts=tuple(item.get("rebuts", [])),
                )
            )
        except (KeyError, ValueError) as exc:
            raise DebateParsingError(f"{role} claim #{i} malformed: {item!r}") from exc
    return claims


@dataclass
class Verdict:
    decision: str
    reasoning: str
    cited_claim_ids: tuple[str, ...]
    order: str  # "advocate_first" | "challenger_first"


INDECIDABLE = "indécidable — information manquante"

JUDGE_SYSTEM_PROMPT = (
    "You are the judge. You do not debate. Weigh arguments by the credibility "
    "of the evidence they cite; the consensus/credibility scores given below "
    "are signals, not a verdict you must follow. Require citations by ID. "
    'Respond ONLY with JSON: {{"decision": str, "reasoning": str, '
    '"cited_claim_ids": [str]}}. If the evidence is insufficient or '
    f'contradictory beyond resolution, decision must be exactly "{INDECIDABLE}".'
)


def _run_judge_pass(
    llm_client: LLMClient,
    model: str,
    question: str,
    claims_in_order: Sequence[Claim],
    s_scores: dict,
    c_scores: dict,
    order_label: str,
) -> Verdict:
    claims_text = "\n".join(
        f"[{c.id}] ({c.author_role}, {c.stance.value}) {c.text} "
        f"(cites: {', '.join(c.cited_evidence_ids) or 'none'})"
        for c in claims_in_order
    )
    prompt = (
        f"Question: {question}\n\nClaims (order: {order_label}):\n{claims_text}\n\n"
        f"Consensus scores S(o): {s_scores}\nArgument credibility C(a_i): {c_scores}"
    )
    raw = llm_client.complete(prompt, model=model, system=JUDGE_SYSTEM_PROMPT)
    try:
        parsed = json.loads(raw)
        return Verdict(
            decision=parsed["decision"],
            reasoning=parsed["reasoning"],
            cited_claim_ids=tuple(parsed.get("cited_claim_ids", [])),
            order=order_label,
        )
    except (json.JSONDecodeError, KeyError) as exc:
        raise DebateParsingError(f"judge output malformed: {raw!r}") from exc


def double_pass_judge(
    llm_client: LLMClient,
    model: str,
    question: str,
    advocate_claims: Sequence[Claim],
    challenger_claims: Sequence[Claim],
    s_scores: dict,
    c_scores: dict,
) -> tuple[Verdict, Verdict, str]:
    """Judge runs twice with reversed claim order (v3 correction F6). If the
    two decisions diverge, the pipeline verdict is forced to "indécidable"
    regardless of what either individual pass said (v3 correction F6)."""
    pass_1 = _run_judge_pass(
        llm_client, model, question, list(advocate_claims) + list(challenger_claims), s_scores, c_scores, "advocate_first"
    )
    pass_2 = _run_judge_pass(
        llm_client, model, question, list(challenger_claims) + list(advocate_claims), s_scores, c_scores, "challenger_first"
    )
    if pass_1.decision == pass_2.decision:
        final_decision = pass_1.decision
    else:
        final_decision = f"{INDECIDABLE} (divergence inter-passage)"
    return pass_1, pass_2, final_decision
