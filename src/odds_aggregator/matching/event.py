from __future__ import annotations

from collections import Counter
from datetime import UTC
from decimal import Decimal
from uuid import UUID

from .models import CandidateEvidence, DecisionPlan, EventCandidate, EventInput, MatchState
from .normalization import best_name_similarity, normalize_role, rounded_score
from .scoring_common import _best_two, _hard_rejection_evidence, _ordered, _ranked

_EVENT_AUTO = Decimal("0.90")
_EVENT_MARGIN = Decimal("0.05")
_EVENT_PLAUSIBLE = Decimal("0.78")


def _participant_ids(source: EventInput) -> tuple[UUID, ...] | None:
    if any(participant.canonical_id is None for participant in source.participants):
        return None
    return tuple(
        participant.canonical_id
        for participant in source.participants
        if participant.canonical_id is not None
    )


def _role_map_source(source: EventInput) -> dict[str, UUID] | None:
    pairs: list[tuple[str, UUID]] = []
    for participant in source.participants:
        role = normalize_role(participant.role)
        if role is None or participant.canonical_id is None:
            return None
        pairs.append((role, participant.canonical_id))
    if len({role for role, _ in pairs}) != len(pairs):
        return None
    return dict(pairs)


def _role_map_candidate(candidate: EventCandidate) -> dict[str, UUID] | None:
    pairs: list[tuple[str, UUID]] = []
    for participant in candidate.participants:
        role = normalize_role(participant.role)
        if role is None:
            return None
        pairs.append((role, participant.participant_id))
    if len({role for role, _ in pairs}) != len(pairs):
        return None
    return dict(pairs)


def _position_map_source(source: EventInput) -> dict[int, UUID] | None:
    pairs: list[tuple[int, UUID]] = []
    for participant in source.participants:
        if participant.position is None or participant.canonical_id is None:
            return None
        pairs.append((participant.position, participant.canonical_id))
    if len({position for position, _ in pairs}) != len(pairs):
        return None
    return dict(pairs)


def _position_map_candidate(candidate: EventCandidate) -> dict[int, UUID] | None:
    pairs: list[tuple[int, UUID]] = []
    for participant in candidate.participants:
        if participant.position is None:
            return None
        pairs.append((participant.position, participant.participant_id))
    if len({position for position, _ in pairs}) != len(pairs):
        return None
    return dict(pairs)


def event_windows_seconds(sport_code: str) -> tuple[int, int]:
    if sport_code.strip().casefold() == "tennis":
        return 6 * 60 * 60, 48 * 60 * 60
    return 30 * 60, 24 * 60 * 60


def decide_event(
    source: EventInput,
    candidates: tuple[EventCandidate, ...],
) -> DecisionPlan:
    if source.is_live or normalize_role(source.status) == "live":
        return DecisionPlan(
            state=MatchState.REJECTED,
            canonical_id=None,
            reason_code="out_of_scope_live",
            evidence={"is_live": source.is_live, "status": normalize_role(source.status)},
        )
    participant_ids = _participant_ids(source)
    if participant_ids is None:
        return DecisionPlan(
            state=MatchState.UNRESOLVED,
            canonical_id=None,
            reason_code="parent_unresolved",
            evidence={
                "unresolved_participant_count": sum(
                    participant.canonical_id is None for participant in source.participants
                )
            },
        )
    if len(participant_ids) < 2:
        return DecisionPlan(
            state=MatchState.UNRESOLVED,
            canonical_id=None,
            reason_code="insufficient_participant_evidence",
            evidence={"resolved_participant_count": len(participant_ids)},
        )
    if len(set(participant_ids)) != len(participant_ids):
        return DecisionPlan(
            state=MatchState.REJECTED,
            canonical_id=None,
            reason_code="invalid_participant_shape",
            evidence={"resolved_participant_count": len(participant_ids)},
        )
    source_role_tokens = [
        normalize_role(participant.role)
        for participant in source.participants
        if normalize_role(participant.role) is not None
    ]
    if len(source_role_tokens) != len(set(source_role_tokens)):
        return DecisionPlan(
            state=MatchState.REJECTED,
            canonical_id=None,
            reason_code="invalid_participant_role_shape",
            evidence={
                "duplicate_role_count": len(source_role_tokens) - len(set(source_role_tokens))
            },
        )
    source_position_values = [
        participant.position
        for participant in source.participants
        if participant.position is not None
    ]
    if len(source_position_values) != len(set(source_position_values)):
        return DecisionPlan(
            state=MatchState.REJECTED,
            canonical_id=None,
            reason_code="invalid_participant_position_shape",
            evidence={
                "duplicate_position_count": len(source_position_values)
                - len(set(source_position_values))
            },
        )
    if source.competition_source_id is not None and source.competition_id is None:
        return DecisionPlan(
            state=MatchState.UNRESOLVED,
            canonical_id=None,
            reason_code="parent_unresolved",
            evidence={"competition_source_id": source.competition_source_id},
        )

    automatic_window, guard_window = event_windows_seconds(source.sport_code)
    source_set = set(participant_ids)
    source_role_map = _role_map_source(source)
    source_position_map = _position_map_source(source)
    scored: list[CandidateEvidence] = []
    rejected: Counter[str] = Counter()
    duplicate_risks: Counter[str] = Counter()

    for candidate in candidates:
        if candidate.sport_id != source.sport_id:
            rejected["sport_conflict"] += 1
            continue
        candidate_ids = tuple(participant.participant_id for participant in candidate.participants)
        if len(candidate_ids) != len(participant_ids) or set(candidate_ids) != source_set:
            rejected["participant_shape_conflict"] += 1
            continue
        if (
            source.competition_id is not None
            and candidate.competition_id is not None
            and source.competition_id != candidate.competition_id
        ):
            rejected["competition_conflict"] += 1
            continue

        delta_seconds = abs(
            (
                source.start_time.astimezone(UTC)
                - candidate.start_time.astimezone(UTC)
            ).total_seconds()
        )
        if delta_seconds > guard_window:
            continue

        candidate_roles = _role_map_candidate(candidate)
        candidate_positions = _position_map_candidate(candidate)
        comparable_role = source_role_map is not None and candidate_roles is not None
        comparable_position = (
            not comparable_role
            and source_position_map is not None
            and candidate_positions is not None
        )
        if comparable_role and source_role_map != candidate_roles:
            duplicate_risks["duplicate_risk_role_conflict"] += 1
            continue
        if comparable_position and source_position_map != candidate_positions:
            duplicate_risks["duplicate_risk_position_conflict"] += 1
            continue
        if delta_seconds > automatic_window:
            duplicate_risks["duplicate_risk_time_window"] += 1
            continue

        role_score = Decimal("1") if comparable_role or comparable_position else Decimal("0.5")
        delta = Decimal(str(delta_seconds))
        automatic = Decimal(automatic_window)
        time_score = Decimal("1") - Decimal("0.5") * (delta / automatic)
        competition_score = (
            Decimal("1")
            if source.competition_id is not None
            and candidate.competition_id is not None
            and source.competition_id == candidate.competition_id
            else Decimal("0.5")
        )
        name_score = (
            Decimal("0.5")
            if source.name is None or candidate.name is None
            else best_name_similarity(source.name, candidate.name, ())
        )
        score = (
            Decimal("0.50")
            + Decimal("0.10") * role_score
            + Decimal("0.25") * time_score
            + Decimal("0.10") * competition_score
            + Decimal("0.05") * name_score
        )
        scored.append(
            CandidateEvidence(
                candidate_id=candidate.id,
                rank=0,
                score=score,
                name_score=name_score,
                components={
                    "participant_shape": Decimal("1"),
                    "role": role_score,
                    "time": time_score,
                    "competition": competition_score,
                    "name": name_score,
                },
                reason_codes=(f"time_delta_seconds:{delta_seconds:g}",),
            )
        )

    ordered = _ordered(scored)
    best, runner = _best_two(scored)
    margin = None if best is None or runner is None else best - runner
    plausible = [
        item
        for item in ordered
        if item.score is not None and item.score >= _EVENT_PLAUSIBLE
    ]
    evidence: dict[str, object] = {
        "candidate_count": len(scored),
        "plausible_candidate_count": len(plausible),
        "automatic_window_seconds": automatic_window,
        "guard_window_seconds": guard_window,
        "duplicate_risk_count": sum(duplicate_risks.values()),
        "duplicate_risk_reasons": dict(sorted(duplicate_risks.items())),
        **_hard_rejection_evidence(rejected),
    }

    if best is not None and ordered and margin is not None:
        if best >= _EVENT_AUTO and margin >= _EVENT_MARGIN:
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
            if best is not None and margin is not None and margin < _EVENT_MARGIN
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
    if duplicate_risks:
        for reason in (
            "duplicate_risk_role_conflict",
            "duplicate_risk_position_conflict",
            "duplicate_risk_time_window",
        ):
            if duplicate_risks[reason]:
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
