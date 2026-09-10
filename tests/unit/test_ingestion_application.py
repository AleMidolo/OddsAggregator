from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from odds_aggregator.application.ingestion import (
    BookmakerIdentity,
    ConnectorIngestionService,
    EventIdentityResolution,
    PersistedBatchResult,
    ResolvedEventIdentity,
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
    def __init__(self, *, accept_event: bool = True) -> None:
        self.active = False
        self.accept_event = accept_event
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

    def resolve_event_identity(self, **_: object) -> EventIdentityResolution:
        self._record("store:identity")
        if not self.accept_event:
            return EventIdentityResolution(identity=None, reason_code="participant:ambiguous")
        return EventIdentityResolution(
            identity=ResolvedEventIdentity(
                event_id=UUID(int=3),
                sport_id=UUID(int=2),
                participant_ids={"team-a": UUID(int=4), "team-b": UUID(int=5)},
            )
        )

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
async def test_identity_resolution_happens_between_network_calls() -> None:
    store = RecordingStore()
    result = await ConnectorIngestionService(store, now=lambda: NOW).ingest(
        RecordingConnector(store)
    )

    assert result.quotes_appended == 1
    assert result.events_skipped == 0
    assert store.calls == [
        "store:resolve",
        "store:start",
        "network:list_sports",
        "store:sport",
        "network:list_events",
        "store:identity",
        "network:get_markets",
        "store:batch",
        "store:finish",
    ]


@pytest.mark.asyncio
async def test_nonaccepted_identity_skips_market_fetch_and_persistence() -> None:
    store = RecordingStore(accept_event=False)
    result = await ConnectorIngestionService(store, now=lambda: NOW).ingest(
        RecordingConnector(store)
    )

    assert result.events_persisted == 0
    assert result.events_skipped == 1
    assert result.markets_persisted == 0
    assert result.quotes_appended == 0
    assert "network:get_markets" not in store.calls
    assert "store:batch" not in store.calls
    assert store.calls == [
        "store:resolve",
        "store:start",
        "network:list_sports",
        "store:sport",
        "network:list_events",
        "store:identity",
        "store:finish",
    ]
