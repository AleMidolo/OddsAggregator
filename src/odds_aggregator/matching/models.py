from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

RULE_VERSION = "prematch-v1"


class MatchState(StrEnum):
    REUSED = "reused"
    MATCHED = "matched"
    CREATED = "created"
    AMBIGUOUS = "ambiguous"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"


class CandidateDisposition(StrEnum):
    ELIGIBLE = "eligible"
    HARD_REJECTED = "hard_rejected"


@dataclass(frozen=True, slots=True)
class CompetitionInput:
    source_id: str
    sport_id: UUID
    name: str
    country_code: str | None = None
    season: str | None = None
    gender: str | None = None


@dataclass(frozen=True, slots=True)
class ParticipantInput:
    source_id: str
    sport_id: UUID
    name: str
    participant_type: str | None = None
    country_code: str | None = None


@dataclass(frozen=True, slots=True)
class EventParticipantInput:
    source_id: str
    canonical_id: UUID | None
    role: str | None = None
    position: int | None = None


@dataclass(frozen=True, slots=True)
class EventInput:
    source_id: str
    sport_id: UUID
    sport_code: str
    start_time: datetime
    name: str | None = None
    competition_source_id: str | None = None
    competition_id: UUID | None = None
    participants: tuple[EventParticipantInput, ...] = ()
    status: str = "scheduled"
    is_live: bool = False

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None or self.start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CompetitionCandidate:
    id: UUID
    sport_id: UUID
    name: str
    country_code: str | None = None
    season: str | None = None
    gender: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParticipantCandidate:
    id: UUID
    sport_id: UUID
    name: str
    participant_type: str
    country_code: str | None = None
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EventParticipantCandidate:
    participant_id: UUID
    role: str | None = None
    position: int | None = None


@dataclass(frozen=True, slots=True)
class EventCandidate:
    id: UUID
    sport_id: UUID
    start_time: datetime
    name: str | None = None
    competition_id: UUID | None = None
    participants: tuple[EventParticipantCandidate, ...] = ()

    def __post_init__(self) -> None:
        if self.start_time.tzinfo is None or self.start_time.utcoffset() is None:
            raise ValueError("start_time must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CandidateEvidence:
    candidate_id: UUID
    rank: int
    score: Decimal | None
    disposition: CandidateDisposition = CandidateDisposition.ELIGIBLE
    reason_codes: tuple[str, ...] = ()
    name_score: Decimal | None = None
    components: dict[str, Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MatchOutcome:
    state: MatchState
    canonical_id: UUID | None
    reason_code: str
    source_fingerprint: str | None = None
    decision_key: str | None = None
    decision_id: UUID | None = None
    best_score: Decimal | None = None
    runner_up_score: Decimal | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    candidates: tuple[CandidateEvidence, ...] = ()


@dataclass(frozen=True, slots=True)
class DecisionPlan:
    state: MatchState
    canonical_id: UUID | None
    reason_code: str
    best_score: Decimal | None = None
    runner_up_score: Decimal | None = None
    evidence: dict[str, object] = field(default_factory=dict)
    candidates: tuple[CandidateEvidence, ...] = ()
