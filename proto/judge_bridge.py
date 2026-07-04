"""CLI bridge for Phase 1 (v3 1.1-1.2, v4 addition): lets the Claude-Code
native `debate-judge` agent (`.claude/agents/debate-judge.md`) get a
mechanically-built argument graph, credibility scores, and consensus score
without reimplementing conflict detection as LLM reasoning.

Conflict detection must stay non-LLM (v4 invariant, pipeline step [5]) even
in Flux C, which otherwise runs entirely inside a Claude Code chat session --
this script is the bridge that keeps that invariant true there too. Per Flux
C (`CLAUDE.md`), the *orchestrator* invokes this script via Bash after
collecting both sides' structured claims, then hands the resulting JSON to
the judge subagent as a scoring signal -- the judge itself never runs this
script or the raw conflict-detection logic.

Usage:
    python -m proto.judge_bridge --evidence evidence.json --claims claims.json
    python -m proto.judge_bridge --evidence evidence.json --claims claims.json --as-of 2026-07-03 --theta 0.6

evidence.json: {"evidence": [Evidence.to_dict(), ...]}
claims.json:   {"claims": [Claim.to_dict(), ...]}   (advocate + challenger claims together)

Prints one JSON object to stdout:
{
  "graph": ArgumentGraph.to_dict(),
  "credibility": {claim_id: C(a_i), ...},
  "consensus": {"score": S(o), "theta": theta}
}
Exits non-zero with a message on stderr if the input is malformed, so the
invoking agent gets clear feedback rather than a silently wrong graph.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from proto.argument_graph import ArgumentGraph, Claim, Evidence
from proto.scoring import (
    DEFAULT_THETA,
    TrustWeightStore,
    argument_credibility,
    consensus_score,
    stances_from_claims,
)


class JudgeBridgeError(RuntimeError):
    """Malformed input -- reported on stderr with exit code 1."""


def build_graph_report(
    evidence: list[Evidence],
    claims: list[Claim],
    as_of: date,
    theta: float = DEFAULT_THETA,
    trust_weight_store: TrustWeightStore | None = None,
) -> dict:
    graph = ArgumentGraph()
    for e in evidence:
        graph.add_evidence(e)
    for c in claims:
        graph.add_claim(c)
    graph.detect_conflicts()

    evidence_by_id = {e.id: e for e in evidence}
    credibility = {c.id: argument_credibility(c, evidence_by_id, as_of) for c in graph.claims}

    trust_weights = trust_weight_store or TrustWeightStore()
    stances = stances_from_claims(graph.claims)
    score = consensus_score(stances, trust_weights.all_weights())

    return {
        "graph": graph.to_dict(),
        "credibility": credibility,
        "consensus": {"score": score, "theta": theta},
    }


def _load_evidence(path: Path) -> list[Evidence]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Evidence.from_dict(e) for e in data["evidence"]]
    except FileNotFoundError as exc:
        raise JudgeBridgeError(f"evidence file not found: {path}") from exc
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise JudgeBridgeError(f"malformed evidence file {path}: {exc}") from exc


def _load_claims(path: Path) -> list[Claim]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Claim.from_dict(c) for c in data["claims"]]
    except FileNotFoundError as exc:
        raise JudgeBridgeError(f"claims file not found: {path}") from exc
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise JudgeBridgeError(f"malformed claims file {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evidence", required=True, type=Path, help="JSON file: {\"evidence\": [...]}")
    parser.add_argument("--claims", required=True, type=Path, help="JSON file: {\"claims\": [...]} (both sides)")
    parser.add_argument("--as-of", type=date.fromisoformat, default=None, help="YYYY-MM-DD, defaults to today")
    parser.add_argument("--theta", type=float, default=DEFAULT_THETA)
    parser.add_argument("--trust-weights", type=Path, default=None, help="override results/trust_weights.json path")
    args = parser.parse_args(argv)

    try:
        evidence = _load_evidence(args.evidence)
        claims = _load_claims(args.claims)
        store = TrustWeightStore(path=args.trust_weights) if args.trust_weights else None
        report = build_graph_report(evidence, claims, args.as_of or date.today(), args.theta, store)
    except JudgeBridgeError as exc:
        print(f"judge_bridge error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
