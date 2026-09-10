"""Shared bookmaker-agnostic connector DTOs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator


def _require_timezone_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return value


AwareDatetime = Annotated[datetime, AfterValidator(_require_timezone_aware)]
ValidDecimalOdds = Annotated[Decimal, Field(gt=Decimal("1"))]


class ConnectorDTO(BaseModel):
    """Base configuration for immutable shared connector DTOs."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ConnectorHealthStatus(StrEnum):
    DISABLED = "disabled"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    THROTTLED = "throttled"
    CIRCUIT_OPEN = "circuit_open"
    CONFIGURATION_ERROR = "configuration_error"


class SourceEventStatus(StrEnum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    SUSPENDED = "suspended"
    FINISHED = "finished"
    CANCELLED = "cancelled"
    POSTPONED = "postponed"
    UNKNOWN = "unknown"


class SourceMarketStatus(StrEnum):
    OPEN = "open"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class ConnectorHealth(ConnectorDTO):
    status: ConnectorHealthStatus
    checked_at: AwareDatetime
    message: str | None = None


class SourceSport(ConnectorDTO):
    source_id: str
    name: str
    code: str | None = None
    metadata: Mapping[str, object] = Field(default_factory=dict)


class SourceCompetition(ConnectorDTO):
    source_id: str
    sport_source_id: str
    name: str
    country_code: str | None = None
    season: str | None = None
    metadata: Mapping[str, object] = Field(default_factory=dict)


class SourceParticipant(ConnectorDTO):
    source_id: str
    name: str
    participant_type: str | None = None
    metadata: Mapping[str, object] = Field(default_factory=dict)


class SourceEventParticipant(ConnectorDTO):
    source_id: str
    role: str | None = None
    position: int | None = None
    participant: SourceParticipant | None = None

    @model_validator(mode="after")
    def participant_details_match_reference(self) -> SourceEventParticipant:
        if self.participant is not None and self.participant.source_id != self.source_id:
            raise ValueError(
                "embedded participant source_id must match event participant source_id"
            )
        return self


class SourceEvent(ConnectorDTO):
    source_id: str
    sport_source_id: str
    competition_source_id: str | None = None
    competition: SourceCompetition | None = None
    name: str | None = None
    participants: tuple[SourceEventParticipant, ...] = ()
    start_time: AwareDatetime
    status: SourceEventStatus = SourceEventStatus.UNKNOWN
    is_live: bool = False
    source_updated_at: AwareDatetime | None = None
    metadata: Mapping[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def competition_details_match_references(self) -> SourceEvent:
        if self.competition is None:
            return self
        if self.competition.source_id != self.competition_source_id:
            raise ValueError(
                "embedded competition source_id must match event competition_source_id"
            )
        if self.competition.sport_source_id != self.sport_source_id:
            raise ValueError(
                "embedded competition sport_source_id must match event sport_source_id"
            )
        return self


class SourcePrice(ConnectorDTO):
    decimal_odds: ValidDecimalOdds | None = None
    is_available: bool = True
    source_updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def available_price_requires_odds(self) -> SourcePrice:
        if self.is_available and self.decimal_odds is None:
            raise ValueError("available price requires decimal_odds")
        return self


class SourceSelection(ConnectorDTO):
    source_id: str | None = None
    label: str
    selection_type: str | None = None
    participant_source_id: str | None = None
    line: Decimal | None = None
    price: SourcePrice
    metadata: Mapping[str, object] = Field(default_factory=dict)


class SourceMarket(ConnectorDTO):
    source_id: str
    event_source_id: str
    name: str | None = None
    market_type: str | None = None
    period: str | None = None
    scope: str | None = None
    line: Decimal | None = None
    status: SourceMarketStatus = SourceMarketStatus.UNKNOWN
    selections: tuple[SourceSelection, ...] = ()
    source_updated_at: AwareDatetime | None = None
    metadata: Mapping[str, object] = Field(default_factory=dict)


class EventFeedRequest(ConnectorDTO):
    sport_source_id: str | None = None
    competition_source_id: str | None = None
    since: AwareDatetime | None = None
    cursor: str | None = None


class EventFeedResult(ConnectorDTO):
    events: tuple[SourceEvent, ...] = ()
    next_cursor: str | None = None


class MarketFeedRequest(ConnectorDTO):
    event_source_id: str
    cursor: str | None = None


class MarketFeedResult(ConnectorDTO):
    markets: tuple[SourceMarket, ...] = ()
    next_cursor: str | None = None
