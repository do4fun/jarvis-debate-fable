"""Measurement primitives for Phase 2 (v3 2.3, revised): precision/recall of
error detection, "invérifiable" routing accuracy (tests F1 -- no evidence
must never produce a fabricated verdict), and false-negative rate isolated
to post-cutoff claims (tests F2). Pure functions over (prediction, ground
truth) pairs -- usable now; real numbers are pending real content in
`datasets/facts/` (currently empty, deferred alongside `datasets/archi/` per
the Phase 1 status).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from proto.fact_verification import ClaimVerdict

ERROR_LABELS = frozenset({"contredit"})


@dataclass(frozen=True)
class GroundTruthClaim:
    claim_id: str
    label: str  # "soutenu" | "soutenu_faible" | "contredit" | "invérifiable"
    is_post_cutoff: bool = False
    has_evidence: bool = True


def error_detection_precision_recall(
    predictions: Sequence[ClaimVerdict], ground_truth: Sequence[GroundTruthClaim]
) -> dict:
    """"contredit" is the positive class (an error was detected). Iterates
    over `ground_truth` (the reference set to evaluate): a ground-truth
    claim with no matching prediction counts as "no error predicted" (fn if
    it was actually an error, tn otherwise) -- a claim the pipeline never
    produced a verdict for is a miss, not something to silently drop.
    Predictions with no matching ground-truth entry are ignored (outside
    the evaluated set)."""
    pred_by_id = {p.claim_id: p for p in predictions}
    tp = fp = fn = tn = 0
    for gt in ground_truth:
        pred = pred_by_id.get(gt.claim_id)
        predicted_error = pred is not None and pred.label in ERROR_LABELS
        actual_error = gt.label in ERROR_LABELS
        if predicted_error and actual_error:
            tp += 1
        elif predicted_error and not actual_error:
            fp += 1
        elif not predicted_error and actual_error:
            fn += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {"precision": precision, "recall": recall, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def inverifiable_routing_accuracy(
    predictions: Sequence[ClaimVerdict], ground_truth: Sequence[GroundTruthClaim]
) -> float:
    """Rate of claims with no evidence (`has_evidence=False`) correctly
    routed to "invérifiable" -- directly tests correction F1 (never guess a
    verdict when there is nothing to check against). Returns 0.0 (not NaN)
    when no such claim exists in the ground truth, so callers can always
    treat the result as a plain float."""
    no_evidence = [g for g in ground_truth if not g.has_evidence]
    if not no_evidence:
        return 0.0
    pred_by_id = {p.claim_id: p for p in predictions}
    correct = 0
    for g in no_evidence:
        pred = pred_by_id.get(g.claim_id)
        if pred is not None and pred.label == "invérifiable":
            correct += 1
    return correct / len(no_evidence)


def post_cutoff_false_negative_rate(
    predictions: Sequence[ClaimVerdict], ground_truth: Sequence[GroundTruthClaim]
) -> float:
    """False negatives isolated to post-cutoff claims that are actually
    errors (ground truth "contredit") -- directly tests correction F2
    (post-cutoff claims must be evaluated on evidence alone, not model
    memory, which would otherwise miss them)."""
    post_cutoff_errors = [g for g in ground_truth if g.is_post_cutoff and g.label in ERROR_LABELS]
    if not post_cutoff_errors:
        return 0.0
    pred_by_id = {p.claim_id: p for p in predictions}
    missed = 0
    for g in post_cutoff_errors:
        pred = pred_by_id.get(g.claim_id)
        if pred is None or pred.label not in ERROR_LABELS:
            missed += 1
    return missed / len(post_cutoff_errors)
