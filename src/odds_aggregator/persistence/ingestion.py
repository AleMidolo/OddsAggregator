"""PostgreSQL adapter for connector-to-canonical ingestion batches."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from odds_aggregator.application.ingestion import (
    BookmakerIdentity,
    BookmakerNotConfiguredError,
    EventIngestionBatch,
    IngestionStore,
    PersistedBatchResult,
    SelectionObservation,
    SportObservation,
)
from odds_aggregator.domain.models import OddsQuote
from odds_aggregator.domain.observations import build_observation_key

from .ingestion_entities import (
    persist_event_entities,
    persist_market_entity,
    persist_selection_entity,
    persist_sport_entity,
)
from .ingestion_snapshots import persist_market_snapshot
from .models import BookmakerRecord, ConnectorRunRecord
from .repositories import SQLAlchemyHistoricalOddsRepository


class SQLAlchemyIngestionStore(IngestionStore):
    """Persist logical batches with one short transaction per store call."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def resolve_bookmaker(self, bookmaker_code: str) -> BookmakerIdentity:
        with self._session_factory() as session:
            record = session.scalar(
                select(BookmakerRecord).where(BookmakerRecord.code == bookmaker_code)
            )
            if record is None or not record.enabled:
                raise BookmakerNotConfiguredError(
                    f"bookmaker '{bookmaker_code}' is not configured and enabled"
                )
            return BookmakerIdentity(id=record.id, code=record.code)

    def start_run(
        self,
        *,
        run_id: UUID,
        bookmaker_id: UUID,
        operation: str,
        started_at: datetime,
    ) -> None:
        with self._session_factory() as session, session.begin():
            session.add(
                ConnectorRunRecord(
                    id=run_id,
                    bookmaker_id=bookmaker_id,
                    operation=operation,
                    scope=None,
                    started_at=started_at,
                    finished_at=None,
                    status="running",
                    attempt_count=1,
                    received_count=0,
                    accepted_count=0,
                    rejected_count=0,
                    error_code=None,
                    error_summary=None,
                )
            )

    def persist_sport(
        self,
        *,
        bookmaker_id: UUID,
        sport: SportObservation,
        seen_at: datetime,
    ) -> UUID:
        with self._session_factory() as session, session.begin():
            return persist_sport_entity(
                session,
                bookmaker_id=bookmaker_id,
                sport=sport,
                seen_at=seen_at,
            )

    def persist_event_batch(
        self,
        *,
        bookmaker_id: UUID,
        run_id: UUID,
        batch: EventIngestionBatch,
        observed_at: datetime,
    ) -> PersistedBatchResult:
        with self._session_factory() as session, session.begin():
            context = persist_event_entities(
                session,
                bookmaker_id=bookmaker_id,
                batch=batch,
                seen_at=observed_at,
            )
            odds = SQLAlchemyHistoricalOddsRepository(session)
            selections_persisted = 0
            quotes_appended = 0

            for market in batch.markets:
                if market.event_source_id != batch.event.source_id:
                    raise ValueError(
                        "market event_source_id does not match the enclosing event source_id"
                    )
                market_id = persist_market_entity(
                    session,
                    bookmaker_id=bookmaker_id,
                    event_id=context.event_id,
                    market=market,
                    seen_at=observed_at,
                )
                selection_rows: list[tuple[UUID, SelectionObservation]] = []
                for selection in market.selections:
                    selection_id = persist_selection_entity(
                        session,
                        bookmaker_id=bookmaker_id,
                        market_id=market_id,
                        sport_id=context.sport_id,
                        selection=selection,
                        participant_ids=context.participant_ids,
                        seen_at=observed_at,
                    )
                    selection_rows.append((selection_id, selection))
                    selections_persisted += 1

                snapshot_id = persist_market_snapshot(
                    session,
                    bookmaker_id=bookmaker_id,
                    market_id=market_id,
                    run_id=run_id,
                    market=market,
                    is_live=batch.event.is_live,
                    observed_at=observed_at,
                )
                for selection_id, selection in selection_rows:
                    source_updated_at = (
                        selection.source_updated_at
                        or market.source_updated_at
                        or batch.event.source_updated_at
                    )
                    observation_key = build_observation_key(
                        bookmaker_id=bookmaker_id,
                        selection_id=selection_id,
                        decimal_odds=selection.decimal_odds,
                        is_available=selection.is_available,
                        observed_at=observed_at,
                        source_updated_at=source_updated_at,
                    )
                    if odds.append(
                        OddsQuote(
                            snapshot_id=snapshot_id,
                            bookmaker_id=bookmaker_id,
                            selection_id=selection_id,
                            decimal_odds=selection.decimal_odds,
                            is_available=selection.is_available,
                            observed_at=observed_at,
                            source_updated_at=source_updated_at,
                            observation_key=observation_key,
                        )
                    ):
                        quotes_appended += 1

            return PersistedBatchResult(
                markets_persisted=len(batch.markets),
                selections_persisted=selections_persisted,
                quotes_appended=quotes_appended,
            )

    def finish_run(
        self,
        *,
        run_id: UUID,
        finished_at: datetime,
        succeeded: bool,
        received_count: int,
        accepted_count: int,
        error_summary: str | None = None,
    ) -> None:
        with self._session_factory() as session, session.begin():
            record = session.get(ConnectorRunRecord, run_id)
            if record is None:
                raise RuntimeError(f"connector run {run_id} does not exist")
            record.finished_at = finished_at
            record.status = "succeeded" if succeeded else "failed"
            record.received_count = received_count
            record.accepted_count = accepted_count
            record.rejected_count = 0
            record.error_summary = error_summary
