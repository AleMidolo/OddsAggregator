"""Canonical sport and market/selection persistence helpers for connector ingestion."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from odds_aggregator.application.ingestion import (
    MarketObservation,
    SelectionObservation,
    SportObservation,
)
from odds_aggregator.domain.canonical_ids import canonical_entity_id
from odds_aggregator.domain.models import SourceEntityMapping, SourceEntityType

from .models import MarketRecord, SelectionRecord, SportRecord
from .repositories import SQLAlchemySourceMappingRepository

_INTERNAL_NAMESPACE = UUID("120ddf53-4180-4b56-a91e-66bd57ac1b78")


def persist_sport_entity(
    session: Session,
    *,
    bookmaker_id: UUID,
    sport: SportObservation,
    seen_at: datetime,
) -> UUID:
    mappings = SQLAlchemySourceMappingRepository(session)
    existing = mappings.get(
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.SPORT,
        source_id=sport.source_id,
    )
    code = _sport_code(sport)
    canonical_id = (
        existing.canonical_id
        if existing is not None
        else canonical_entity_id(bookmaker_id, SourceEntityType.SPORT.value, sport.source_id)
    )
    session.execute(
        insert(SportRecord)
        .values(id=canonical_id, code=code, name=sport.name)
        .on_conflict_do_nothing()
    )
    record = session.get(SportRecord, canonical_id)
    if record is not None:
        record.name = sport.name
    elif existing is None:
        code_match = session.scalar(select(SportRecord).where(SportRecord.code == code))
        if code_match is None:
            raise RuntimeError("sport insert did not produce a persisted row")
        canonical_id = code_match.id
    else:
        raise RuntimeError("existing sport mapping points to a missing canonical row")

    _touch_mapping(
        mappings,
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.SPORT,
        source_id=sport.source_id,
        canonical_id=canonical_id,
        source_name=sport.name,
        seen_at=seen_at,
    )
    return canonical_id


def persist_market_entity(
    session: Session,
    *,
    bookmaker_id: UUID,
    event_id: UUID,
    market: MarketObservation,
    seen_at: datetime,
) -> UUID:
    mappings = SQLAlchemySourceMappingRepository(session)
    existing = mappings.get(
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.MARKET,
        source_id=market.source_id,
    )
    canonical_id = (
        existing.canonical_id
        if existing is not None
        else canonical_entity_id(bookmaker_id, SourceEntityType.MARKET.value, market.source_id)
    )
    market_type = market.market_type or "unknown"
    period = market.period or "unknown"
    session.execute(
        insert(MarketRecord)
        .values(
            id=canonical_id,
            event_id=event_id,
            market_type=market_type,
            period=period,
            line=market.line,
            scope=market.scope,
            variant=None,
            created_at=seen_at,
            updated_at=seen_at,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "event_id": event_id,
                "market_type": market_type,
                "period": period,
                "line": market.line,
                "scope": market.scope,
                "updated_at": seen_at,
            },
        )
    )
    _touch_mapping(
        mappings,
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.MARKET,
        source_id=market.source_id,
        canonical_id=canonical_id,
        source_name=market.name,
        seen_at=seen_at,
    )
    return canonical_id


def persist_selection_entity(
    session: Session,
    *,
    bookmaker_id: UUID,
    market_id: UUID,
    selection: SelectionObservation,
    participant_ids: Mapping[str, UUID],
    seen_at: datetime,
) -> UUID:
    mappings = SQLAlchemySourceMappingRepository(session)
    participant_id: UUID | None = None
    if selection.participant_source_id is not None:
        participant_id = participant_ids.get(selection.participant_source_id)
        if participant_id is None:
            participant_mapping = mappings.get(
                bookmaker_id=bookmaker_id,
                entity_type=SourceEntityType.PARTICIPANT,
                source_id=selection.participant_source_id,
            )
            if participant_mapping is not None:
                participant_id = participant_mapping.canonical_id

    existing = None
    if selection.source_id is not None:
        existing = mappings.get(
            bookmaker_id=bookmaker_id,
            entity_type=SourceEntityType.SELECTION,
            source_id=selection.source_id,
        )
    if existing is not None:
        canonical_id = existing.canonical_id
    elif selection.source_id is not None:
        canonical_id = canonical_entity_id(
            bookmaker_id,
            SourceEntityType.SELECTION.value,
            selection.source_id,
        )
    else:
        canonical_id = uuid5(
            _INTERNAL_NAMESPACE,
            f"selection:{_selection_identity(market_id, selection)}",
        )

    selection_type = selection.selection_type or "unknown"
    session.execute(
        insert(SelectionRecord)
        .values(
            id=canonical_id,
            market_id=market_id,
            selection_type=selection_type,
            participant_id=participant_id,
            line=selection.line,
            name=selection.label,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "market_id": market_id,
                "selection_type": selection_type,
                "participant_id": participant_id,
                "line": selection.line,
                "name": selection.label,
            },
        )
    )
    if selection.source_id is not None:
        _touch_mapping(
            mappings,
            bookmaker_id=bookmaker_id,
            entity_type=SourceEntityType.SELECTION,
            source_id=selection.source_id,
            canonical_id=canonical_id,
            source_name=selection.label,
            seen_at=seen_at,
        )
    return canonical_id


def _sport_code(sport: SportObservation) -> str:
    raw = sport.code or sport.name
    normalized = "-".join(raw.strip().casefold().split())
    if normalized:
        return normalized[:64]
    return f"source-{hashlib.sha256(sport.source_id.encode()).hexdigest()[:12]}"


def _touch_mapping(
    mappings: SQLAlchemySourceMappingRepository,
    *,
    bookmaker_id: UUID,
    entity_type: SourceEntityType,
    source_id: str,
    canonical_id: UUID,
    source_name: str | None,
    seen_at: datetime,
) -> None:
    mappings.upsert(
        SourceEntityMapping(
            bookmaker_id=bookmaker_id,
            entity_type=entity_type,
            source_id=source_id,
            canonical_id=canonical_id,
            source_name=source_name,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
    )


def _selection_identity(market_id: UUID, selection: SelectionObservation) -> str:
    line = "" if selection.line is None else format(selection.line.normalize(), "f")
    return "|".join(
        (
            str(market_id),
            selection.selection_type or "unknown",
            selection.participant_source_id or "",
            line,
            selection.label,
        )
    )
