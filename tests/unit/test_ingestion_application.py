from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from odds_aggregator.application.ingestion import (
    BookmakerIdentity,
    ConnectorIngestionService,
    PersistedBatchResult,
)
from odds_aggregator.connectors import (
    ConnectorHealth,
    ConnectorHealthStatus,
    EventFeedResult,
    MarketFeedResult,
    SourceEvent,
    SourceEventParticipant,
    SourceMarket,
    SourcePrice,
    SourceSelection,
    SourceSport,
)

NOW = datetime(2026, 9, 9, 12, tzinfo=UTC)


class RecordingStore:
    def __init__(self) -> None:
        self.active = False
        self.calls: list[str] = []

    def _record(self, name: str) -> None:
        assert not self.active
        self.active = True
        self.calls.append(name)
        self.active = False

    def resolve_bookmaker(self, bookmaker_code: str) -> BookmakerIdentity:
        self._record("store:resolve")
        return BookmakerIdentity(id=UUID(int=1), code=bookmaker_code)

    def start_run(self, **_: object) -> None:
        self._record("store:start")

    def persist_sport(self, **_: object) -> UUID:
        self._record("store:sport")
        return UUID(int=2)

    def persist_event_batch(self, **_: object) -> PersistedBatchResult:
        self._record("store:batch")
        return PersistedBatchResult(
            markets_persisted=1,
            selections_persisted=1,
            quotes_appended=1,
        )

    def finish_run(self, **_: object) -> None:
        self._record("store:finish")


class RecordingConnector:
    bookmaker_code = "fixture"

    def __init__(self, store: RecordingStore) -> None:
        self.store = store

    def _record_network(self, name: str) -> None:
        assert not self.store.active
        self.store.calls.append(name)

    async def health(self) -> ConnectorHealth:
        self._record_network("network:health")
        return ConnectorHealth(status=ConnectorHealthStatus.HEALTHY, checked_at=NOW)

    async def list_sports(self) -> list[SourceSport]:
        self._record_network("network:list_sports")
        return [SourceSport(source_id="sport-1", name="Football", code="football")]

    async def list_events(self, request: object) -> EventFeedResult:
        self._record_network("network:list_events")
        return EventFeedResult(
            events=(
                SourceEvent(
                    source_id="event-1",
                    sport_source_id="sport-1",
                    competition_source_id="competition-1",
                    name="A v B",
                    participants=(
                        SourceEventParticipant(source_id="team-a", role="home"),
                        SourceEventParticipant(source_id="team-b", role="away"),
                    ),
                    start_time=NOW,
                    source_updated_at=NOW,
                ),
            )
        )

    async def get_markets(self, request: object) -> MarketFeedResult:
        self._record_network("network:get_markets")
        return MarketFeedResult(
            markets=(
                SourceMarket(
                    source_id="market-1",
                    event_source_id="event-1",
                    market_type="moneyline",
                    period="full_time",
                    source_updated_at=NOW,
                    selections=(
                        SourceSelection(
                            source_id="selection-1",
                            label="A",
                            selection_type="home",
                            participant_source_id="team-a",
                            price=SourcePrice(
                                decimal_odds=Decimal("2.10"),
                                source_updated_at=NOW,
                            ),
                        ),
                    ),
                ),
            )
        )


@pytest.mark.asyncio
async def test_network_calls_happen_between_short_store_calls() -> None:
    store = RecordingStore()
    result = await ConnectorIngestionService(store, now=lambda: NOW).ingest(
        RecordingConnector(store)
    )

    assert result.quotes_appended == 1
    assert store.calls == [
        "store:resolve",
        "store:start",
        "network:list_sports",
        "store:sport",
        "network:list_events",
        "network:get_markets",
        "store:batch",
        "store:finish",
    ]
