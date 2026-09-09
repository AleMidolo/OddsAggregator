"""Deterministic fixture connector used by shared tests."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from .dtos import (
    ConnectorHealth,
    ConnectorHealthStatus,
    EventFeedRequest,
    EventFeedResult,
    MarketFeedRequest,
    MarketFeedResult,
    SourceEvent,
    SourceMarket,
    SourceSport,
)
from .errors import ConnectorError


@dataclass(slots=True)
class FakeBookmakerConnector:
    bookmaker_code: str = "fake"
    sports: tuple[SourceSport, ...] = ()
    events: tuple[SourceEvent, ...] = ()
    markets_by_event: Mapping[str, tuple[SourceMarket, ...]] = field(default_factory=dict)
    failure_plan: Mapping[str, tuple[ConnectorError, ...]] = field(default_factory=dict)
    delays_seconds: Mapping[str, float] = field(default_factory=dict)
    health_value: ConnectorHealth = field(
        default_factory=lambda: ConnectorHealth(
            status=ConnectorHealthStatus.HEALTHY,
            checked_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    )
    attempts: dict[str, int] = field(default_factory=dict, init=False)

    async def _before(self, operation: str) -> None:
        attempt = self.attempts.get(operation, 0)
        self.attempts[operation] = attempt + 1
        delay = self.delays_seconds.get(operation, 0.0)
        if delay > 0:
            await asyncio.sleep(delay)
        failures = self.failure_plan.get(operation, ())
        if attempt < len(failures):
            raise failures[attempt]

    async def health(self) -> ConnectorHealth:
        await self._before("health")
        return self.health_value

    async def list_sports(self) -> list[SourceSport]:
        await self._before("list_sports")
        return list(self.sports)

    async def list_events(self, request: EventFeedRequest) -> EventFeedResult:
        await self._before("list_events")
        events = self.events
        if request.sport_source_id is not None:
            events = tuple(
                event for event in events if event.sport_source_id == request.sport_source_id
            )
        if request.competition_source_id is not None:
            events = tuple(
                event
                for event in events
                if event.competition_source_id == request.competition_source_id
            )
        return EventFeedResult(events=events)

    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult:
        await self._before("get_markets")
        return MarketFeedResult(markets=self.markets_by_event.get(request.event_source_id, ()))
