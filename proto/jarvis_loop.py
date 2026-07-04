"""Phase 3 -- Jarvis conversational-loop harness (v3 Phase 3, v4 3.1
addition): decide whether a live question goes through a debate or gets a
direct answer, and measure end-to-end latency (3.3).

**Routing criteria (3.2) are an explicit open decision** ("critères du
routeur : définis plus tard, hors périmètre actuel" -- v3 décisions actées,
unchanged in v4). This module does NOT invent them: `router` is a
caller-supplied predicate. `default_router` is a placeholder that always
answers directly, so nothing silently routes to a debate until real
criteria are decided and wired in -- it must never be mistaken for a
considered heuristic.

3.1 (v4): web research stays off by default in the conversational loop
(latency + the "debate runs offline" invariant) -- `enable_web_research`
here defaults to False and overrides whatever `debate_config` was built
with, rather than trusting the caller not to forget it. Explicit opt-in is
for veille/monitoring queries only (criteria also pending, 3.2).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Callable

from proto.llm_client import LLMClient
from proto.pipeline import DebateConfig, PipelineResult, run_pipeline

RouterFn = Callable[[str], bool]

# 3.3: proposed, not validated -- mirrors DECISION.md's own process (propose
# after first runs, then get explicit user validation before treating it as
# a real go/no-go gate).
DEFAULT_LATENCY_THRESHOLD_S = 5.0

DIRECT_ANSWER_SYSTEM_PROMPT = (
    "Answer the question directly and concisely, using only the local "
    "corpus/context you are given -- no live web access (the conversational "
    "loop runs offline)."
)


def default_router(question: str) -> bool:
    """Placeholder: 3.2 criteria are not yet defined, so this always
    answers directly. Replace with the real router once criteria are
    decided -- do not extend this function with ad hoc heuristics."""
    return False


@dataclass
class ConversationalAnswer:
    question: str
    routed_to_debate: bool
    answer: str
    latency_s: float
    pipeline_result: PipelineResult | None = None


def answer_or_debate(
    question: str,
    llm_client: LLMClient,
    debate_config: DebateConfig,
    direct_model: str,
    *,
    router: RouterFn = default_router,
    enable_web_research: bool = False,
    **pipeline_kwargs: object,
) -> ConversationalAnswer:
    """3.1: reuses whichever config won Phase 2's evaluation, passed in as
    `debate_config` -- there is no single hardcoded "winning config" here,
    since Phase 2 hasn't been measured against real data yet (`datasets/facts/`
    is still empty). `enable_web_research` forces the debate path's research
    step off by default regardless of what `debate_config` was built with.
    """
    started = time.monotonic()
    if router(question):
        config = replace(debate_config, enable_web_research=enable_web_research)
        result = run_pipeline(question, config, llm_client, **pipeline_kwargs)
        answer_text = result.verdict
        routed = True
    else:
        result = None
        answer_text = llm_client.complete(question, model=direct_model, system=DIRECT_ANSWER_SYSTEM_PROMPT)
        routed = False
    latency = time.monotonic() - started
    return ConversationalAnswer(
        question=question, routed_to_debate=routed, answer=answer_text,
        latency_s=latency, pipeline_result=result,
    )


def meets_latency_threshold(latency_s: float, threshold_s: float = DEFAULT_LATENCY_THRESHOLD_S) -> bool:
    return latency_s <= threshold_s
