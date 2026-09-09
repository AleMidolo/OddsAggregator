"""Bookmaker-agnostic connector-to-canonical ingestion orchestration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID, uuid4

from odds_aggregator.connectors import (
    BookmakerConnector,
    EventFeedRequest,
    MarketFeedRequest,
    SourceEvent,
    SourceEventStatus,
    SourceMarket,
    SourceMarketStatus,
    SourceSport,
)


class BookmakerNotConfiguredError(RuntimeError):
    """Raised when a connector has no enabled bookmaker configuration."""


@dataclass(frozen=True, slots=True)
class BookmakerIdentity:
    id: UUID
    code: str


@dataclass(frozen=True, slots=True)
class SportObservation:
    source_id: str
    name: str
    code: str | None


@dataclass(frozen=True, slots=True)
class CompetitionObservation:
    source_id: str
    name: str


@dataclass(frozen=True, slots=True)
class ParticipantObservation:
    source_id: str
    name: str
    participant_type: str | None
    role: str | None
    position: int | None


@dataclass(frozen=True, slots=True)
class SelectionObservation:
    source_id: str | None
    label: str
    selection_type: str | None
    participant_source_id: str | None
    line: Decimal | None
    decimal_odds: Decimal | None
    is_available: bool
    source_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class MarketObservation:
    source_id: str
    event_source_id: str
    name: str | None
    market_type: str | None
    period: str | None
    scope: str | None
    line: Decimal | None
    status: SourceMarketStatus
    selections: tuple[SelectionObservation, ...]
    source_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class EventObservation:
    source_id: str
    sport_source_id: str
    competition: CompetitionObservation | None
    name: str | None
    participants: tuple[ParticipantObservation, ...]
    start_time: datetime
    status: SourceEventStatus
    is_live: bool
    source_updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class EventIngestionBatch:
    event: EventObservation
    markets: tuple[MarketObservation, ...]


@dataclass(frozen=True, slots=True)
class PersistedBatchResult:
    markets_persisted: int
    selections_persisted: int
    quotes_appended: int


@dataclass(frozen=True, slots=True)
class IngestionResult:
    run_id: UUID
    bookmaker_code: str
    sports_persisted: int
    events_persisted: int
    markets_persisted: int
    selections_persisted: int
    quotes_appended: int


class IngestionStore(Protocol):
    """Persistence port whose methods own short, synchronous transactions."""

    def resolve_bookmaker(self, bookmaker_code: str) -> BookmakerIdentity: ...

    def start_run(
        self,
        *,
        run_id: UUID,
        bookmaker_id: UUID,
        operation: str,
        started_at: datetime,
    ) -> None: ...

    def persist_sport(
        self,
        *,
        bookmaker_id: UUID,
        sport: SportObservation,
        seen_at: datetime,
    ) -> UUID: ...

    def persist_event_batch(
        self,
        *,
        bookmaker_id: UUID,
        run_id: UUID,
        batch: EventIngestionBatch,
        observed_at: datetime,
    ) -> PersistedBatchResult: ...

    def finish_run(
        self,
        *,
        run_id: UUID,
        finished_at: datetime,
        succeeded: bool,
        received_count: int,
        accepted_count: int,
        error_summary: str | None = None,
    ) -> None: ...


class ConnectorIngestionService:
    """Fetch connector DTOs, then persist each logical batch outside network I/O."""

    def __init__(
        self,
        store: IngestionStore,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._now = now or (lambda: datetime.now(UTC))

    async def ingest(
        self,
        connector: BookmakerConnector,
        *,
        since: datetime | None = None,
    ) -> IngestionResult:
        bookmaker = self._store.resolve_bookmaker(connector.bookmaker_code)
        run_id = uuid4()
        started_at = self._now()
        self._store.start_run(
            run_id=run_id,
            bookmaker_id=bookmaker.id,
            operation="connector_ingestion",
            started_at=started_at,
        )

        sports_persisted = 0
        events_persisted = 0
        markets_persisted = 0
        selections_persisted = 0
        quotes_appended = 0

        try:
            source_sports = await connector.list_sports()
            for source_sport in source_sports:
                self._store.persist_sport(
                    bookmaker_id=bookmaker.id,
                    sport=_sport_observation(source_sport),
                    seen_at=self._now(),
                )
                sports_persisted += 1

            for source_sport in source_sports:
                cursor: str | None = None
                while True:
                    event_result = await connector.list_events(
                        EventFeedRequest(
                            sport_source_id=source_sport.source_id,
                            since=since,
                            cursor=cursor,
                        )
                    )
                    for source_event in event_result.events:
                        source_markets = await self._fetch_markets(
                            connector, source_event.source_id
                        )
                        batch_result = self._store.persist_event_batch(
                            bookmaker_id=bookmaker.id,
                            run_id=run_id,
                            batch=_event_batch(source_event, source_markets),
                            observed_at=self._now(),
                        )
                        events_persisted += 1
                        markets_persisted += batch_result.markets_persisted
                        selections_persisted += batch_result.selections_persisted
                        quotes_appended += batch_result.quotes_appended

                    cursor = event_result.next_cursor
                    if cursor is None:
                        break

        except Exception as error:
            self._store.finish_run(
                run_id=run_id,
                finished_at=self._now(),
                succeeded=False,
                received_count=events_persisted + markets_persisted + selections_persisted,
                accepted_count=quotes_appended,
                error_summary=str(error)[:1000],
            )
            raise

        self._store.finish_run(
            run_id=run_id,
            finished_at=self._now(),
            succeeded=True,
            received_count=events_persisted + markets_persisted + selections_persisted,
            accepted_count=quotes_appended,
        )
        return IngestionResult(
            run_id=run_id,
            bookmaker_code=bookmaker.code,
            sports_persisted=sports_persisted,
            events_persisted=events_persisted,
            markets_persisted=markets_persisted,
            selections_persisted=selections_persisted,
            quotes_appended=quotes_appended,
        )

    async def _fetch_markets(
        self,
        connector: BookmakerConnector,
        event_source_id: str,
    ) -> tuple[SourceMarket, ...]:
        markets: list[SourceMarket] = []
        cursor: str | None = None
        while True:
            result = await connector.get_markets(
                MarketFeedRequest(event_source_id=event_source_id, cursor=cursor)
            )
            markets.extend(result.markets)
            cursor = result.next_cursor
            if cursor is None:
                return tuple(markets)


def _sport_observation(source: SourceSport) -> SportObservation:
    return SportObservation(source_id=source.source_id, name=source.name, code=source.code)


def _event_batch(
    source_event: SourceEvent,
    source_markets: tuple[SourceMarket, ...],
) -> EventIngestionBatch:
    competition = None
    if source_event.competition_source_id is not None:
        competition = CompetitionObservation(
            source_id=source_event.competition_source_id,
            name=source_event.competition_source_id,
        )

    participants = tuple(
        ParticipantObservation(
            source_id=participant.source_id,
            name=participant.source_id,
            participant_type=None,
            role=participant.role,
            position=participant.position,
        )
        for participant in source_event.participants
    )
    markets = tuple(_market_observation(market) for market in source_markets)
    return EventIngestionBatch(
        event=EventObservation(
            source_id=source_event.source_id,
            sport_source_id=source_event.sport_source_id,
            competition=competition,
            name=source_event.name,
            participants=participants,
            start_time=source_event.start_time,
            status=source_event.status,
            is_live=source_event.is_live,
            source_updated_at=source_event.source_updated_at,
        ),
        markets=markets,
    )


def _market_observation(source: SourceMarket) -> MarketObservation:
    selections = tuple(
        SelectionObservation(
            source_id=selection.source_id,
            label=selection.label,
            selection_type=selection.selection_type,
            participant_source_id=selection.participant_source_id,
            line=selection.line,
            decimal_odds=(
                selection.price.decimal_odds if selection.price.is_available else None
            ),
            is_available=selection.price.is_available,
            source_updated_at=selection.price.source_updated_at,
        )
        for selection in source.selections
    )
    return MarketObservation(
        source_id=source.source_id,
        event_source_id=source.event_source_id,
        name=source.name,
        market_type=source.market_type,
        period=source.period,
        scope=source.scope,
        line=source.line,
        status=source.status,
        selections=selections,
        source_updated_at=source.source_updated_at,
    )
