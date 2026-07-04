"""Phase 4 (v3 4.2, v4 addition): standardized JSON documentation of
retained AND rejected patterns, with F1-F9/Axe-2.4 correction traceability
and trust_weight drift curves -- "pour que la base documentaire garde la
mémoire des raisons d'architecture, pas seulement le résultat."

This module is the *reporting tool*, not the retain/reject decision. No
pattern below has actually been retained or rejected yet: Phase 1-3's
evaluation protocols (1.3, 2.2-2.3, 3.3-3.4) haven't run against real data
(`datasets/archi/` and `datasets/facts/` are still empty). `default_patterns()`
documents what exists today, all marked "en_attente" -- update each entry's
`status` to "retenu" or "rejeté" once a real go/no-go happens, don't
overwrite this module to fake one.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from proto.scoring import TrustWeightStore

DEFAULT_REPORT_PATH = Path("results/pattern_report.json")


@dataclass
class PatternEntry:
    name: str
    phase: str
    status: str  # "retenu" | "rejeté" | "en_attente"
    corrections: tuple[str, ...] = field(default_factory=tuple)  # e.g. ("F1", "F4")
    source_files: tuple[str, ...] = field(default_factory=tuple)
    rationale: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "phase": self.phase,
            "status": self.status,
            "corrections": list(self.corrections),
            "source_files": list(self.source_files),
            "rationale": self.rationale,
        }


def default_patterns() -> list[PatternEntry]:
    """Traceability of every pattern implemented so far, per the v3
    corrections table and the v4 features table -- all "en_attente" since
    nothing has been validated against real data yet."""
    return [
        PatternEntry("Filtre pré-débat (1 appel judge seul)", "2.1", "en_attente",
                     corrections=("F1", "F2", "F4"),
                     source_files=("proto/fact_verification.py",),
                     rationale="Court-circuite le débat si le juge seul est confiant ; réserve le débat aux claims incertains."),
        PatternEntry("Débat sur évidence, jamais sur mémoire", "0.6/2.1", "en_attente",
                     corrections=("F1", "F2"),
                     source_files=("proto/acquire.py", "proto/evidence_match.py", "proto/debate_local.py"),
                     rationale="Fiche de faits sourcée obligatoire ; mémoire paramétrique disqualifiée post-cutoff."),
        PatternEntry("Arrêt anticipé conditionné aux citations concordantes", "1.2", "en_attente",
                     corrections=("F3",),
                     source_files=("CLAUDE.md", "proto/pipeline.py"),
                     rationale="Convergence sans citations concordantes n'arrête pas le débat (anti-sycophancie)."),
        PatternEntry("Résumé structuré inter-tours + tour 2 mécanique", "1.2/Axe3", "en_attente",
                     corrections=("F5",),
                     source_files=(".claude/agents/debate-advocate.md", ".claude/agents/debate-challenger.md",
                                   "proto/pipeline.py", "proto/debate_local.py"),
                     rationale="Jamais de prose complète transmise entre tours -- résumé à format imposé. "
                               "Tour 2 déclenché uniquement si le tour 1 ne converge pas (détection mécanique "
                               "de conflits sur les claims structurés), aussi bien côté proto/ que Flux C."),
        PatternEntry("Juge double passage, ordre inversé", "Invariants/1.2/2.1", "en_attente",
                     corrections=("F6",),
                     source_files=("proto/debate_local.py", "proto/fact_verification.py", ".claude/agents/debate-judge.md"),
                     rationale="Divergence entre passages -> indécidable, jamais un arbitrage dépendant de l'ordre."),
        PatternEntry("Baseline self-consistency à budget compute égal", "0.2/1.3/2.3", "en_attente",
                     corrections=("F7",),
                     source_files=("proto/baseline.py",),
                     rationale="Comparaison au débat toujours à budget d'appels égal, jamais 1 appel vs N."),
        PatternEntry("Extraction verbatim + fidélité traduction FR/EN", "0.2/0.4", "en_attente",
                     corrections=("F8",),
                     source_files=("proto/translate_enrich.py",),
                     rationale="Tokens sensibles protégés de la traduction ; test aller-retour mesuré (pas encore exécuté)."),
        PatternEntry("Double variante jeux de test (avec/sans contraintes)", "0.3/1.3", "en_attente",
                     corrections=("F9",),
                     source_files=("datasets/archi/",),
                     rationale="Isole la valeur ajoutée du débat de la simple application de contraintes -- contenu réel pas encore fourni."),
        PatternEntry("Invalidation de verdict par hash au re-crawl", "0.5/2.4", "en_attente",
                     corrections=("Axe 2.4",),
                     source_files=("proto/verdict_store.py",),
                     rationale="Un verdict n'est valide que tant que le hash de l'évidence citée ne change pas."),
        PatternEntry("Pipeline à 7 étapes", "Architecture pipeline/1.2/2.1", "en_attente",
                     corrections=(), source_files=("proto/pipeline.py",),
                     rationale="Séquence les 3 rôles (advocate/challenger/juge) + outillage non-LLM, sans ajouter d'agent."),
        PatternEntry("Recherche web à point d'ancrage unique", "Étape [1]/0.4-0.6", "en_attente",
                     corrections=(), source_files=("proto/acquire.py", "docs/PLAN_recherche_web.md"),
                     rationale="2 appels LLM max pour toute la phase de recherche ; réseau clos avant le débat."),
        PatternEntry("Argument graph + détection de conflits mécanique", "Étapes [5]-[6]/1.2/2.1", "en_attente",
                     corrections=(), source_files=("proto/argument_graph.py", "proto/judge_bridge.py"),
                     rationale="Arêtes attack/support dérivées des citations par ID, jamais devinées par un LLM."),
        PatternEntry("Consensus S(o) et seuil θ", "Scoring/0.2", "en_attente",
                     corrections=(), source_files=("proto/scoring.py",),
                     rationale="Signal d'entrée du juge, jamais un remplacement de son verdict."),
        PatternEntry("Crédibilité C(a_i) (niveau × fraîcheur)", "Scoring", "en_attente",
                     corrections=(), source_files=("proto/scoring.py",),
                     rationale="N1/N2/N3 × décroissance de fraîcheur -- pondérations initiales non validées."),
        PatternEntry("Trust weight EMA persistant, vérité-terrain-only", "Scoring/2.3", "en_attente",
                     corrections=(), source_files=("proto/scoring.py",),
                     rationale="Jamais mis à jour sur le simple accord inter-agents (garde-fou anti-boucle de renforcement)."),
        PatternEntry("Reprise sur interruption (checkpoint par appel/claim)", "0.7", "en_attente",
                     corrections=(), source_files=("proto/checkpoint.py",),
                     rationale="Écriture atomique, reprise exacte sans recalcul des étapes déjà faites."),
        PatternEntry("Log complet par session", "0.5", "en_attente",
                     corrections=(), source_files=("proto/logger.py",),
                     rationale="Toutes les étapes du pipeline tracées, y compris à travers une reprise."),
        PatternEntry("Boucle conversationnelle Jarvis (routeur + latence)", "Phase 3", "en_attente",
                     corrections=(), source_files=("proto/jarvis_loop.py",),
                     rationale="Critères du routeur (3.2) non définis -- default_router est un placeholder, pas une heuristique."),
    ]


def build_pattern_report(
    patterns: Sequence[PatternEntry] | None = None,
    trust_weight_store: TrustWeightStore | None = None,
) -> dict:
    patterns = list(patterns) if patterns is not None else default_patterns()
    store = trust_weight_store or TrustWeightStore()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "patterns": [p.to_dict() for p in patterns],
        "trust_weights_final": store.all_weights(),
        "trust_weights_drift": store.get_history(),
    }


def write_pattern_report(report: dict, path: Path = DEFAULT_REPORT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
