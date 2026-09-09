from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


class ParticipantType(StrEnum):
    TEAM = "team"
    PLAYER = "player"
    PAIR = "pair"
    OTHER = "other"


class EventStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    SUSPENDED = "suspended"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"
    UNKNOWN = "unknown"


class MarketStatus(StrEnum):
    OPEN = "open"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class SourceEntityType(StrEnum):
    SPORT = "sport"
    COMPETITION = "competition"
    PARTICIPANT = "participant"
    EVENT = "event"
    MARKET = "market"
    SELECTION = "selection"


class ConnectorRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    THROTTLED = "throttled"


@dataclass(slots=True)
class Bookmaker:
    code: str
    name: str
    id: UUID = field(default_factory=uuid4)
    enabled: bool = True
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Sport:
    code: str
    name: str
    id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class Competition:
    sport_id: UUID
    name: str
    id: UUID = field(default_factory=uuid4)
    country_code: str | None = None
    gender: str | None = None
    season: str | None = None


@dataclass(slots=True)
class Participant:
    sport_id: UUID
    name: str
    type: ParticipantType
    id: UUID = field(default_factory=uuid4)
    country_code: str | None = None


@dataclass(slots=True)
class Event:
    sport_id: UUID
    start_time: datetime
    status: EventStatus
    is_live: bool
    id: UUID = field(default_factory=uuid4)
    competition_id: UUID | None = None
    name: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_aware(self.start_time, "start_time")


@dataclass(slots=True)
class EventParticipant:
    event_id: UUID
    participant_id: UUID
    role: str | None = None
    position: int | None = None


@dataclass(slots=True)
class Market:
    event_id: UUID
    market_type: str
    period: str
    id: UUID = field(default_factory=uuid4)
    line: Decimal | None = None
    scope: str | None = None
    variant: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class Selection:
    market_id: UUID
    selection_type: str
    id: UUID = field(default_factory=uuid4)
    participant_id: UUID | None = None
    line: Decimal | None = None
    name: str | None = None


@dataclass(slots=True)
class MarketSnapshot:
    bookmaker_id: UUID
    market_id: UUID
    run_id: UUID
    observed_at: datetime
    is_live: bool
    market_status: MarketStatus
    id: UUID = field(default_factory=uuid4)
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_aware(self.observed_at, "observed_at")
        if self.source_updated_at is not None:
            _require_aware(self.source_updated_at, "source_updated_at")


@dataclass(slots=True)
class OddsQuote:
    snapshot_id: UUID
    bookmaker_id: UUID
    selection_id: UUID
    decimal_odds: Decimal
    is_available: bool
    observed_at: datetime
    observation_key: str
    id: UUID = field(default_factory=uuid4)
    source_updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.decimal_odds <= Decimal("1"):
            raise ValueError("decimal_odds must be greater than 1")
        if not self.observation_key:
            raise ValueError("observation_key must not be empty")
        _require_aware(self.observed_at, "observed_at")
        if self.source_updated_at is not None:
            _require_aware(self.source_updated_at, "source_updated_at")


@dataclass(slots=True)
class SourceEntityMapping:
    bookmaker_id: UUID
    entity_type: SourceEntityType
    source_id: str
    canonical_id: UUID
    first_seen_at: datetime
    last_seen_at: datetime
    id: UUID = field(default_factory=uuid4)
    source_name: str | None = None
    connector_version: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id:
            raise ValueError("source_id must not be empty")
        _require_aware(self.first_seen_at, "first_seen_at")
        _require_aware(self.last_seen_at, "last_seen_at")


@dataclass(slots=True)
class ConnectorRun:
    bookmaker_id: UUID
    operation: str
    started_at: datetime
    status: ConnectorRunStatus = ConnectorRunStatus.RUNNING
    id: UUID = field(default_factory=uuid4)
    scope: str | None = None
    finished_at: datetime | None = None
    attempt_count: int = 0
    received_count: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    error_code: str | None = None
    error_summary: str | None = None

    def __post_init__(self) -> None:
        _require_aware(self.started_at, "started_at")
        if self.finished_at is not None:
            _require_aware(self.finished_at, "finished_at")
