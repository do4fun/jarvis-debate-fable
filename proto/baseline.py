"""Self-consistency baseline at equal compute budget (v3 correction F7): if
the debate costs N LLM calls, the baseline samples the same model N times and
takes a majority vote -- never a single-call baseline, which the v2 plan used
and the audit flagged as an unfair comparison."""
from __future__ import annotations

from collections import Counter

from proto.llm_client import LLMClient


def run_self_consistency(
    llm_client: LLMClient,
    model: str,
    prompt: str,
    n_samples: int,
    system: str | None = None,
    temperature: float = 0.8,
) -> dict:
    if n_samples < 1:
        raise ValueError("n_samples must be >= 1")
    samples = [llm_client.complete(prompt, model=model, system=system, temperature=temperature) for _ in range(n_samples)]
    counts = Counter(samples)
    majority, votes = counts.most_common(1)[0]
    return {"majority": majority, "votes": votes, "n_samples": n_samples, "samples": samples}
