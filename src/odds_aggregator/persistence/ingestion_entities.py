"""Canonical entity bootstrap helpers for connector ingestion."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from odds_aggregator.application.ingestion import (
    CompetitionObservation,
    EventIngestionBatch,
    MarketObservation,
    ParticipantObservation,
    SelectionObservation,
    SportObservation,
)
from odds_aggregator.domain.models import SourceEntityMapping, SourceEntityType

from .models import (
    CompetitionRecord,
    EventParticipantRecord,
    EventRecord,
    MarketRecord,
    ParticipantRecord,
    SelectionRecord,
    SportRecord,
)
from .repositories import SQLAlchemySourceMappingRepository

_CANONICAL_NAMESPACE = UUID("120ddf53-4180-4b56-a91e-66bd57ac1b78")


@dataclass(slots=True)
class EventPersistenceContext:
    event_id: UUID
    sport_id: UUID
    participant_ids: dict[str, UUID]


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
        else _canonical_id(bookmaker_id, SourceEntityType.SPORT, sport.source_id)
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


def persist_event_entities(
    session: Session,
    *,
    bookmaker_id: UUID,
    batch: EventIngestionBatch,
    seen_at: datetime,
) -> EventPersistenceContext:
    mappings = SQLAlchemySourceMappingRepository(session)
    sport_mapping = _require_mapping(
        mappings,
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.SPORT,
        source_id=batch.event.sport_source_id,
    )
    competition_id = _ensure_competition(
        session,
        mappings=mappings,
        bookmaker_id=bookmaker_id,
        sport_id=sport_mapping.canonical_id,
        competition=batch.event.competition,
        seen_at=seen_at,
    )
    participant_ids = {
        participant.source_id: _ensure_participant(
            session,
            mappings=mappings,
            bookmaker_id=bookmaker_id,
            sport_id=sport_mapping.canonical_id,
            participant=participant,
            seen_at=seen_at,
        )
        for participant in batch.event.participants
    }
    event_id = _ensure_event(
        session,
        mappings=mappings,
        bookmaker_id=bookmaker_id,
        sport_id=sport_mapping.canonical_id,
        competition_id=competition_id,
        batch=batch,
        participant_ids=participant_ids,
        seen_at=seen_at,
    )
    return EventPersistenceContext(
        event_id=event_id,
        sport_id=sport_mapping.canonical_id,
        participant_ids=participant_ids,
    )


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
        else _canonical_id(bookmaker_id, SourceEntityType.MARKET, market.source_id)
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
    sport_id: UUID,
    selection: SelectionObservation,
    participant_ids: dict[str, UUID],
    seen_at: datetime,
) -> UUID:
    participant_id = None
    if selection.participant_source_id is not None:
        participant_id = participant_ids.get(selection.participant_source_id)
        if participant_id is None:
            participant_id = _ensure_participant(
                session,
                mappings=SQLAlchemySourceMappingRepository(session),
                bookmaker_id=bookmaker_id,
                sport_id=sport_id,
                participant=ParticipantObservation(
                    source_id=selection.participant_source_id,
                    name=selection.participant_source_id,
                    participant_type=None,
                    role=None,
                    position=None,
                ),
                seen_at=seen_at,
            )
            participant_ids[selection.participant_source_id] = participant_id

    mappings = SQLAlchemySourceMappingRepository(session)
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
        canonical_id = _canonical_id(
            bookmaker_id,
            SourceEntityType.SELECTION,
            selection.source_id,
        )
    else:
        canonical_id = uuid5(
            _CANONICAL_NAMESPACE,
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


def _canonical_id(bookmaker_id: UUID, entity_type: SourceEntityType, source_id: str) -> UUID:
    return uuid5(_CANONICAL_NAMESPACE, f"{bookmaker_id}:{entity_type.value}:{source_id}")


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


def _require_mapping(
    mappings: SQLAlchemySourceMappingRepository,
    *,
    bookmaker_id: UUID,
    entity_type: SourceEntityType,
    source_id: str,
) -> SourceEntityMapping:
    mapping = mappings.get(
        bookmaker_id=bookmaker_id,
        entity_type=entity_type,
        source_id=source_id,
    )
    if mapping is None:
        raise ValueError(
            f"missing {entity_type.value} source mapping for '{source_id}' before dependent write"
        )
    return mapping


def _ensure_competition(
    session: Session,
    *,
    mappings: SQLAlchemySourceMappingRepository,
    bookmaker_id: UUID,
    sport_id: UUID,
    competition: CompetitionObservation | None,
    seen_at: datetime,
) -> UUID | None:
    if competition is None:
        return None
    existing = mappings.get(
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.COMPETITION,
        source_id=competition.source_id,
    )
    canonical_id = (
        existing.canonical_id
        if existing is not None
        else _canonical_id(bookmaker_id, SourceEntityType.COMPETITION, competition.source_id)
    )
    session.execute(
        insert(CompetitionRecord)
        .values(
            id=canonical_id,
            sport_id=sport_id,
            name=competition.name,
            country_code=None,
            gender=None,
            season=None,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={"sport_id": sport_id, "name": competition.name},
        )
    )
    _touch_mapping(
        mappings,
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.COMPETITION,
        source_id=competition.source_id,
        canonical_id=canonical_id,
        source_name=competition.name,
        seen_at=seen_at,
    )
    return canonical_id


def _participant_type(value: str | None) -> str:
    if value is not None and value in {"team", "player", "pair", "other"}:
        return value
    return "other"


def _ensure_participant(
    session: Session,
    *,
    mappings: SQLAlchemySourceMappingRepository,
    bookmaker_id: UUID,
    sport_id: UUID,
    participant: ParticipantObservation,
    seen_at: datetime,
) -> UUID:
    existing = mappings.get(
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.PARTICIPANT,
        source_id=participant.source_id,
    )
    canonical_id = (
        existing.canonical_id
        if existing is not None
        else _canonical_id(bookmaker_id, SourceEntityType.PARTICIPANT, participant.source_id)
    )
    participant_type = _participant_type(participant.participant_type)
    session.execute(
        insert(ParticipantRecord)
        .values(
            id=canonical_id,
            sport_id=sport_id,
            type=participant_type,
            name=participant.name,
            country_code=None,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "sport_id": sport_id,
                "type": participant_type,
                "name": participant.name,
            },
        )
    )
    _touch_mapping(
        mappings,
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.PARTICIPANT,
        source_id=participant.source_id,
        canonical_id=canonical_id,
        source_name=participant.name,
        seen_at=seen_at,
    )
    return canonical_id


def _ensure_event(
    session: Session,
    *,
    mappings: SQLAlchemySourceMappingRepository,
    bookmaker_id: UUID,
    sport_id: UUID,
    competition_id: UUID | None,
    batch: EventIngestionBatch,
    participant_ids: dict[str, UUID],
    seen_at: datetime,
) -> UUID:
    event = batch.event
    existing = mappings.get(
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.EVENT,
        source_id=event.source_id,
    )
    canonical_id = (
        existing.canonical_id
        if existing is not None
        else _canonical_id(bookmaker_id, SourceEntityType.EVENT, event.source_id)
    )
    session.execute(
        insert(EventRecord)
        .values(
            id=canonical_id,
            sport_id=sport_id,
            competition_id=competition_id,
            name=event.name,
            start_time=event.start_time,
            status=event.status.value,
            is_live=event.is_live,
            created_at=seen_at,
            updated_at=seen_at,
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "sport_id": sport_id,
                "competition_id": competition_id,
                "name": event.name,
                "start_time": event.start_time,
                "status": event.status.value,
                "is_live": event.is_live,
                "updated_at": seen_at,
            },
        )
    )
    _touch_mapping(
        mappings,
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.EVENT,
        source_id=event.source_id,
        canonical_id=canonical_id,
        source_name=event.name,
        seen_at=seen_at,
    )
    for participant in event.participants:
        participant_id = participant_ids[participant.source_id]
        session.execute(
            insert(EventParticipantRecord)
            .values(
                event_id=canonical_id,
                participant_id=participant_id,
                role=participant.role,
                position=participant.position,
            )
            .on_conflict_do_update(
                index_elements=["event_id", "participant_id"],
                set_={"role": participant.role, "position": participant.position},
            )
        )
    return canonical_id


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
