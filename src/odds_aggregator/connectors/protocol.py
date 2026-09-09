"""Public protocol implemented by every bookmaker connector."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .dtos import (
    ConnectorHealth,
    EventFeedRequest,
    EventFeedResult,
    MarketFeedRequest,
    MarketFeedResult,
    SourceSport,
)


@runtime_checkable
class BookmakerConnector(Protocol):
    bookmaker_code: str

    async def health(self) -> ConnectorHealth: ...

    async def list_sports(self) -> list[SourceSport]: ...

    async def list_events(self, request: EventFeedRequest) -> EventFeedResult: ...

    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult: ...
