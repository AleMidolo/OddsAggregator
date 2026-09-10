from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .models import CandidateEvidence
from .normalization import rounded_score


def _ordered(evidence: list[CandidateEvidence]) -> list[CandidateEvidence]:
    return sorted(
        evidence,
        key=lambda item: (
            -(item.score if item.score is not None else Decimal("-1")),
            str(item.candidate_id),
        ),
    )


def _ranked(evidence: list[CandidateEvidence]) -> tuple[CandidateEvidence, ...]:
    ordered = _ordered(evidence)[:5]
    return tuple(
        CandidateEvidence(
            candidate_id=item.candidate_id,
            rank=index,
            score=rounded_score(item.score),
            disposition=item.disposition,
            reason_codes=item.reason_codes,
            name_score=rounded_score(item.name_score),
            components={
                key: rounded_score(value) or Decimal("0")
                for key, value in item.components.items()
            },
        )
        for index, item in enumerate(ordered, start=1)
    )


def _best_two(evidence: list[CandidateEvidence]) -> tuple[Decimal | None, Decimal | None]:
    ordered = _ordered(evidence)
    if not ordered:
        return None, None
    best = ordered[0].score
    if best is None:
        return None, None
    runner = ordered[1].score if len(ordered) > 1 else Decimal("0")
    return best, runner


def _hard_rejection_evidence(counts: Counter[str]) -> dict[str, object]:
    return {
        "hard_rejection_count": sum(counts.values()),
        "hard_rejection_reasons": dict(sorted(counts.items())),
    }
