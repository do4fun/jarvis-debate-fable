"""The 7-step debate pipeline (v4, feature 1):

  [1] web research -> [2] brainstorming -> [3] thesis -> [4] antithesis ->
  [5] conflict detection -> [6] argument graph -> [7] synthesis

The pipeline sequences the work of three roles (advocate, challenger, judge)
plus non-LLM tooling -- it does not add agents (v4 invariant: "2 débatteurs +
1 juge maximum ... le pipeline à 7 étapes n'ajoute pas d'agents, il séquence
le travail des trois rôles"). Checkpointed after every LLM call so an
interrupted run resumes at the exact step (feature 9), and every step is
written to a full session log (feature 10).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable, Literal

from proto import acquire, debate_local
from proto.argument_graph import ArgumentGraph, Claim, Evidence
from proto.checkpoint import CheckpointStore
from proto.debate_local import Verdict
from proto.llm_client import LLMClient
from proto.logger import SessionLogger
from proto.scoring import DEFAULT_THETA, TrustWeightStore, argument_credibility, consensus_score, stances_from_claims

STEP_ORDER = (
    "web_research",
    "brainstorming",
    "thesis",
    "antithesis",
    "rebuttal",
    "conflict_detection",
    "argument_graph",
    "synthesis",
)


@dataclass
class AgentPersona:
    name: str
    role: Literal["advocate", "challenger", "judge", "researcher", "brainstormer"]
    model: str
    system_prompt: str = ""


@dataclass
class DebateConfig:
    advocate: AgentPersona
    challenger: AgentPersona
    judge: AgentPersona
    researcher: AgentPersona | None = None
    brainstormer: AgentPersona | None = None
    phase_models: dict[str, str] = field(default_factory=dict)
    speaking_order: Literal["sequential", "parallel", "dependencies"] = "parallel"
    theta: float = DEFAULT_THETA
    enable_web_research: bool = True
    searxng_base_url: str = "http://localhost:8080"
    whitelist_n1: tuple[str, ...] = ()
    whitelist_n2: tuple[str, ...] = ()

    def model_for(self, phase: str, default_persona: AgentPersona) -> str:
        """`phase_models` override (v4 feature 4); falls back to the
        persona's own model when the phase has no override."""
        return self.phase_models.get(phase, default_persona.model)


@dataclass
class PipelineResult:
    session_id: str
    question: str
    graph: ArgumentGraph
    verdict: str
    judge_pass_1: Verdict
    judge_pass_2: Verdict
    s_scores: dict
    c_scores: dict
    log_path: str


def run_pipeline(
    question: str,
    config: DebateConfig,
    llm_client: LLMClient,
    *,
    session_id: str | None = None,
    checkpoint_store: CheckpointStore | None = None,
    trust_weight_store: TrustWeightStore | None = None,
    session_logger: SessionLogger | None = None,
    as_of: date | None = None,
    research_search_fn: Callable[[str, str], list[dict]] | None = None,
    research_extract_fn: Callable[[str], dict] | None = None,
    research_corpus_raw_dir: Path | None = None,
) -> PipelineResult:
    session_id = session_id or str(uuid.uuid4())
    checkpoints = checkpoint_store or CheckpointStore()
    trust_weights = trust_weight_store or TrustWeightStore()
    as_of = as_of or date.today()
    logger = session_logger or SessionLogger(session_id=session_id)

    existing = checkpoints.load(session_id)
    state: dict = dict(existing.state) if existing else {}
    # Resuming: seed the session log with steps already completed before the
    # interruption, so the final log stays complete (feature 10) even though
    # this run only re-executes what's left (feature 9).
    for step in STEP_ORDER:
        if step in state:
            logger.log_step(step, **state[step])

    def done(step: str) -> bool:
        return step in state

    def checkpoint(step: str, payload: dict) -> None:
        state[step] = payload
        checkpoints.save(session_id, step, state)
        logger.log_step(step, **payload)

    # [1] Recherche web -- une seule fois par débat, puis close (v4 feature 2).
    # Désactivable (DebateConfig.enable_web_research) -- off par défaut prévu
    # en boucle conversationnelle Phase 3.
    evidence: list[Evidence] = []
    if config.enable_web_research:
        if done("web_research"):
            evidence = [Evidence.from_dict(e) for e in state["web_research"]["evidence"]]
        else:
            researcher = config.researcher or config.judge
            model = config.model_for("web_research", researcher)
            anchor_query = acquire.formulate_anchor_query(llm_client, model, question)
            search_kwargs = {}
            if research_corpus_raw_dir is not None:
                search_kwargs["corpus_raw_dir"] = research_corpus_raw_dir
            candidates = acquire.search_and_archive(
                anchor_query,
                searxng_base_url=config.searxng_base_url,
                whitelist_n1=config.whitelist_n1,
                whitelist_n2=config.whitelist_n2,
                search_fn=research_search_fn,
                extract_fn=research_extract_fn,
                **search_kwargs,
            )
            evidence = acquire.validate_sources(llm_client, model, question, candidates)
            checkpoint("web_research", {"anchor_query": anchor_query, "evidence": [e.to_dict() for e in evidence]})

    # [2] Brainstorming -- énumère les options/angles depuis la fiche de faits.
    # Alimente les positions initiales sans les figer (v4) : injecté dans le
    # prompt des tours 1 de thèse/antithèse ci-dessous, non contraignant.
    if done("brainstorming"):
        brainstorm_notes = state["brainstorming"]["notes"]
    else:
        brainstormer = config.brainstormer or config.advocate
        model = config.model_for("brainstorming", brainstormer)
        fact_sheet = "\n".join(f"[{e.id}] {e.excerpt}" for e in evidence)
        brainstorm_notes = llm_client.complete(
            f"Question: {question}\n\nFact sheet:\n{fact_sheet}",
            model=model,
            system="Enumerate the options/angles relevant to this question from the fact sheet only. Be concise.",
        )
        checkpoint("brainstorming", {"notes": brainstorm_notes})

    # [3] Thèse (advocate) -- tour 1
    if done("thesis"):
        advocate_claims_r1 = [Claim.from_dict(c) for c in state["thesis"]["claims"]]
    else:
        model = config.model_for("thesis", config.advocate)
        advocate_claims_r1 = debate_local.generate_position(
            llm_client, model, "advocate", question, evidence, "advocate", brainstorming_notes=brainstorm_notes
        )
        checkpoint("thesis", {"claims": [c.to_dict() for c in advocate_claims_r1]})

    # [4] Antithèse (challenger) -- tour 1, parallèle par défaut : pas de
    # visibilité sur les claims de l'advocate (nécessaire à F3/F9).
    if done("antithesis"):
        challenger_claims_r1 = [Claim.from_dict(c) for c in state["antithesis"]["claims"]]
    else:
        model = config.model_for("antithesis", config.challenger)
        opposing = advocate_claims_r1 if config.speaking_order == "sequential" else ()
        challenger_claims_r1 = debate_local.generate_position(
            llm_client, model, "challenger", question, evidence, "challenger",
            opposing_claims=opposing, brainstorming_notes=brainstorm_notes,
        )
        checkpoint("antithesis", {"claims": [c.to_dict() for c in challenger_claims_r1]})

    # Arrêt anticipé (correction F3) : mécanique, non-LLM -- si le tour 1 ne
    # produit aucun conflit détecté (citations concordantes, pas de rebuttal
    # ni de désaccord sur évidence partagée), le tour 2 est sauté. Sinon,
    # tour 2 obligatoire : chaque débatteur réfute le résumé structuré de
    # l'autre (F5 -- generate_position ne transmet jamais la prose brute,
    # seulement les claims structurés de l'autre tour).
    round1_graph = ArgumentGraph()
    for e in evidence:
        round1_graph.add_evidence(e)
    for c in advocate_claims_r1 + challenger_claims_r1:
        round1_graph.add_claim(c)
    round1_converged = len(round1_graph.detect_conflicts()) == 0

    if done("rebuttal"):
        rebuttal_state = state["rebuttal"]
        if rebuttal_state["skipped"]:
            advocate_claims_r2, challenger_claims_r2 = [], []
        else:
            advocate_claims_r2 = [Claim.from_dict(c) for c in rebuttal_state["advocate_claims"]]
            challenger_claims_r2 = [Claim.from_dict(c) for c in rebuttal_state["challenger_claims"]]
    elif round1_converged:
        advocate_claims_r2, challenger_claims_r2 = [], []
        checkpoint("rebuttal", {"skipped": True, "reason": "tour 1 convergent, citations concordantes (F3)"})
    else:
        model_advocate = config.model_for("rebuttal", config.advocate)
        model_challenger = config.model_for("rebuttal", config.challenger)
        advocate_claims_r2 = debate_local.generate_position(
            llm_client, model_advocate, "advocate", question, evidence, "advocate-r2",
            opposing_claims=challenger_claims_r1,
        )
        challenger_claims_r2 = debate_local.generate_position(
            llm_client, model_challenger, "challenger", question, evidence, "challenger-r2",
            opposing_claims=advocate_claims_r1,
        )
        checkpoint("rebuttal", {
            "skipped": False,
            "advocate_claims": [c.to_dict() for c in advocate_claims_r2],
            "challenger_claims": [c.to_dict() for c in challenger_claims_r2],
        })

    advocate_claims = advocate_claims_r1 + advocate_claims_r2
    challenger_claims = challenger_claims_r1 + challenger_claims_r2

    # [5]+[6] Détection de conflits + argument graph -- mécanique, non-LLM.
    # Reconstruit sur l'ensemble tour 1 + tour 2 (le round1_graph ci-dessus
    # ne servait qu'à la décision d'arrêt anticipé).
    graph = ArgumentGraph()
    for e in evidence:
        graph.add_evidence(e)
    for c in advocate_claims + challenger_claims:
        graph.add_claim(c)
    conflicts = graph.detect_conflicts()
    if not done("conflict_detection"):
        checkpoint("conflict_detection", {"conflicts": len(conflicts)})
    if not done("argument_graph"):
        checkpoint(
            "argument_graph",
            {"claims": len(graph.claims), "evidence": len(graph.evidence), "relations": len(graph.relations)},
        )

    # Signaux pour le juge : S(o) et C(a_i) -- jamais un remplacement du verdict.
    evidence_by_id = {e.id: e for e in evidence}
    c_scores = {c.id: argument_credibility(c, evidence_by_id, as_of) for c in graph.claims}
    stances = stances_from_claims(graph.claims)
    weights = trust_weights.all_weights()
    s_scores = {"consensus": consensus_score(stances, weights), "theta": config.theta}

    # [7] Synthèse (juge, double passage ordre inversé)
    if done("synthesis"):
        synth = state["synthesis"]
        pass_1 = Verdict(**{**synth["pass_1"], "cited_claim_ids": tuple(synth["pass_1"]["cited_claim_ids"])})
        pass_2 = Verdict(**{**synth["pass_2"], "cited_claim_ids": tuple(synth["pass_2"]["cited_claim_ids"])})
        verdict = synth["verdict"]
    else:
        model = config.model_for("synthesis", config.judge)
        pass_1, pass_2, verdict = debate_local.double_pass_judge(
            llm_client, model, question, advocate_claims, challenger_claims, s_scores, c_scores
        )
        checkpoint(
            "synthesis",
            {
                "pass_1": {"decision": pass_1.decision, "reasoning": pass_1.reasoning,
                           "cited_claim_ids": list(pass_1.cited_claim_ids), "order": pass_1.order},
                "pass_2": {"decision": pass_2.decision, "reasoning": pass_2.reasoning,
                           "cited_claim_ids": list(pass_2.cited_claim_ids), "order": pass_2.order},
                "verdict": verdict,
            },
        )

    logger.log_step("graph_snapshot", graph=graph.to_dict())
    log_path = logger.write()
    checkpoints.clear(session_id)  # run completed: no resumable state left

    return PipelineResult(
        session_id=session_id,
        question=question,
        graph=graph,
        verdict=verdict,
        judge_pass_1=pass_1,
        judge_pass_2=pass_2,
        s_scores=s_scores,
        c_scores=c_scores,
        log_path=str(log_path),
    )
