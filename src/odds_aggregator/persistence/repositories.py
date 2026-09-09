from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from odds_aggregator.domain.models import OddsQuote, SourceEntityMapping, SourceEntityType

from .models import OddsQuoteRecord, SourceEntityMappingRecord


class SQLAlchemySourceMappingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(
        self,
        *,
        bookmaker_id: UUID,
        entity_type: SourceEntityType,
        source_id: str,
    ) -> SourceEntityMapping | None:
        record = self._session.scalar(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.bookmaker_id == bookmaker_id,
                SourceEntityMappingRecord.entity_type == entity_type.value,
                SourceEntityMappingRecord.source_id == source_id,
            )
        )
        return None if record is None else _mapping_to_domain(record)

    def upsert(self, mapping: SourceEntityMapping) -> SourceEntityMapping:
        statement = (
            insert(SourceEntityMappingRecord)
            .values(
                id=mapping.id,
                bookmaker_id=mapping.bookmaker_id,
                entity_type=mapping.entity_type.value,
                source_id=mapping.source_id,
                canonical_id=mapping.canonical_id,
                source_name=mapping.source_name,
                first_seen_at=mapping.first_seen_at,
                last_seen_at=mapping.last_seen_at,
                connector_version=mapping.connector_version,
            )
            .on_conflict_do_nothing(
                index_elements=["bookmaker_id", "entity_type", "source_id"]
            )
        )
        self._session.execute(statement)
        record = self._session.scalar(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.bookmaker_id == mapping.bookmaker_id,
                SourceEntityMappingRecord.entity_type == mapping.entity_type.value,
                SourceEntityMappingRecord.source_id == mapping.source_id,
            )
        )
        if record is None:
            raise RuntimeError("source mapping insert did not produce a persisted row")
        if record.canonical_id != mapping.canonical_id:
            raise ValueError("source mapping cannot be reassigned to a different canonical entity")
        if record.id != mapping.id:
            record.last_seen_at = mapping.last_seen_at
            record.source_name = mapping.source_name
            record.connector_version = mapping.connector_version
            self._session.flush()
        return _mapping_to_domain(record)


class SQLAlchemyHistoricalOddsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def append(self, quote: OddsQuote) -> bool:
        statement = (
            insert(OddsQuoteRecord)
            .values(
                id=quote.id,
                snapshot_id=quote.snapshot_id,
                bookmaker_id=quote.bookmaker_id,
                selection_id=quote.selection_id,
                decimal_odds=quote.decimal_odds,
                is_available=quote.is_available,
                observed_at=quote.observed_at,
                source_updated_at=quote.source_updated_at,
                observation_key=quote.observation_key,
            )
            .on_conflict_do_nothing(index_elements=["observation_key"])
            .returning(OddsQuoteRecord.id)
        )
        return self._session.execute(statement).scalar_one_or_none() is not None


def _mapping_to_domain(record: SourceEntityMappingRecord) -> SourceEntityMapping:
    return SourceEntityMapping(
        id=record.id,
        bookmaker_id=record.bookmaker_id,
        entity_type=SourceEntityType(record.entity_type),
        source_id=record.source_id,
        canonical_id=record.canonical_id,
        source_name=record.source_name,
        first_seen_at=record.first_seen_at,
        last_seen_at=record.last_seen_at,
        connector_version=record.connector_version,
    )
