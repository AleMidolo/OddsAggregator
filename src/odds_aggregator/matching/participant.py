from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .models import (
    CandidateEvidence,
    DecisionPlan,
    MatchState,
    ParticipantCandidate,
    ParticipantInput,
)
from .normalization import (
    best_name_similarity,
    metadata_score,
    normalize_country,
    normalize_name,
    normalize_participant_type,
    rounded_score,
)
from .scoring_common import _best_two, _hard_rejection_evidence, _ordered, _ranked

_PARTICIPANT_AUTO = Decimal("0.92")
_PARTICIPANT_NAME_GATE = Decimal("0.94")
_PARTICIPANT_MARGIN = Decimal("0.08")
_PARTICIPANT_PLAUSIBLE = Decimal("0.78")


def decide_participant(
    source: ParticipantInput,
    candidates: tuple[ParticipantCandidate, ...],
) -> DecisionPlan:
    source_name = normalize_name(source.name)
    if not source_name:
        return DecisionPlan(
            state=MatchState.REJECTED,
            canonical_id=None,
            reason_code="invalid_name",
            evidence={"normalized_source_name": ""},
        )

    source_type = normalize_participant_type(source.participant_type)
    source_country = normalize_country(source.country_code)
    scored: list[CandidateEvidence] = []
    rejected: Counter[str] = Counter()

    for candidate in candidates:
        if candidate.sport_id != source.sport_id:
            rejected["sport_conflict"] += 1
            continue
        candidate_type = normalize_participant_type(candidate.participant_type)
        source_concrete = source_type not in {None, "other"}
        candidate_concrete = candidate_type not in {None, "other"}
        if source_concrete and candidate_concrete and source_type != candidate_type:
            rejected["participant_type_conflict"] += 1
            continue

        candidate_country = normalize_country(candidate.country_code)
        name_score = best_name_similarity(source.name, candidate.name, candidate.aliases)
        type_score = (
            Decimal("1")
            if source_concrete and candidate_concrete and source_type == candidate_type
            else Decimal("0.5")
        )
        country_score = metadata_score(
            source_country,
            candidate_country,
            conflict=Decimal("0"),
        )
        score = (
            Decimal("0.80") * name_score
            + Decimal("0.15") * type_score
            + Decimal("0.05") * country_score
        )
        scored.append(
            CandidateEvidence(
                candidate_id=candidate.id,
                rank=0,
                score=score,
                name_score=name_score,
                components={
                    "name": name_score,
                    "type": type_score,
                    "country": country_score,
                },
            )
        )

    ordered = _ordered(scored)
    best, runner = _best_two(scored)
    margin = None if best is None or runner is None else best - runner
    plausible = [
        item
        for item in ordered
        if item.score is not None and item.score >= _PARTICIPANT_PLAUSIBLE
    ]
    evidence: dict[str, object] = {
        "normalized_source_name": source_name,
        "candidate_count": len(scored),
        "plausible_candidate_count": len(plausible),
        **_hard_rejection_evidence(rejected),
    }

    if best is not None and ordered:
        best_name = ordered[0].name_score or Decimal("0")
        if (
            best >= _PARTICIPANT_AUTO
            and best_name >= _PARTICIPANT_NAME_GATE
            and margin is not None
            and margin >= _PARTICIPANT_MARGIN
        ):
            return DecisionPlan(
                state=MatchState.MATCHED,
                canonical_id=ordered[0].candidate_id,
                reason_code="auto_match",
                best_score=rounded_score(best),
                runner_up_score=rounded_score(runner),
                evidence=evidence,
                candidates=_ranked(scored),
            )
    if plausible:
        reason = (
            "insufficient_margin"
            if best is not None and margin is not None and margin < _PARTICIPANT_MARGIN
            else "plausible_candidate_below_auto_threshold"
        )
        return DecisionPlan(
            state=MatchState.AMBIGUOUS,
            canonical_id=None,
            reason_code=reason,
            best_score=rounded_score(best),
            runner_up_score=rounded_score(runner),
            evidence=evidence,
            candidates=_ranked(scored),
        )
    return DecisionPlan(
        state=MatchState.CREATED,
        canonical_id=None,
        reason_code="no_plausible_candidate",
        best_score=rounded_score(best),
        runner_up_score=rounded_score(runner),
        evidence=evidence,
    )
