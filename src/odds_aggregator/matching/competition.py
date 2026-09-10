from __future__ import annotations

from collections import Counter
from decimal import Decimal

from .models import (
    CandidateEvidence,
    CompetitionCandidate,
    CompetitionInput,
    DecisionPlan,
    MatchState,
)
from .normalization import (
    best_name_similarity,
    metadata_score,
    normalize_country,
    normalize_gender,
    normalize_name,
    normalize_season,
    rounded_score,
)
from .scoring_common import _best_two, _hard_rejection_evidence, _ordered, _ranked

_COMPETITION_AUTO = Decimal("0.92")
_COMPETITION_NAME_GATE = Decimal("0.90")
_COMPETITION_MARGIN = Decimal("0.08")
_COMPETITION_PLAUSIBLE = Decimal("0.75")


def decide_competition(
    source: CompetitionInput,
    candidates: tuple[CompetitionCandidate, ...],
) -> DecisionPlan:
    source_name = normalize_name(source.name)
    if not source_name:
        return DecisionPlan(
            state=MatchState.REJECTED,
            canonical_id=None,
            reason_code="invalid_name",
            evidence={"normalized_source_name": ""},
        )

    source_country = normalize_country(source.country_code)
    source_season = normalize_season(source.season)
    source_gender = normalize_gender(source.gender)
    scored: list[CandidateEvidence] = []
    rejected: Counter[str] = Counter()

    for candidate in candidates:
        if candidate.sport_id != source.sport_id:
            rejected["sport_conflict"] += 1
            continue
        country = normalize_country(candidate.country_code)
        season = normalize_season(candidate.season)
        gender = normalize_gender(candidate.gender)
        if source_country is not None and country is not None and source_country != country:
            rejected["country_conflict"] += 1
            continue
        if source_season is not None and season is not None and source_season != season:
            rejected["season_conflict"] += 1
            continue
        if source_gender is not None and gender is not None and source_gender != gender:
            rejected["gender_conflict"] += 1
            continue

        name_score = best_name_similarity(source.name, candidate.name, candidate.aliases)
        country_score = metadata_score(source_country, country)
        season_score = metadata_score(source_season, season)
        gender_score = metadata_score(source_gender, gender)
        score = (
            Decimal("0.70") * name_score
            + Decimal("0.15") * country_score
            + Decimal("0.10") * season_score
            + Decimal("0.05") * gender_score
        )
        scored.append(
            CandidateEvidence(
                candidate_id=candidate.id,
                rank=0,
                score=score,
                name_score=name_score,
                components={
                    "name": name_score,
                    "country": country_score,
                    "season": season_score,
                    "gender": gender_score,
                },
            )
        )

    ordered = _ordered(scored)
    best, runner = _best_two(scored)
    margin = None if best is None or runner is None else best - runner
    plausible = [
        item
        for item in ordered
        if item.score is not None and item.score >= _COMPETITION_PLAUSIBLE
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
            best >= _COMPETITION_AUTO
            and best_name >= _COMPETITION_NAME_GATE
            and margin is not None
            and margin >= _COMPETITION_MARGIN
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
            if best is not None and margin is not None and margin < _COMPETITION_MARGIN
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
