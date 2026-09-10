from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from odds_aggregator.matching.models import (
    CompetitionCandidate,
    EventCandidate,
    EventParticipantCandidate,
    ParticipantCandidate,
)

from .models import (
    CompetitionAliasRecord,
    CompetitionRecord,
    EventParticipantRecord,
    EventRecord,
    ParticipantAliasRecord,
    ParticipantRecord,
    SourceEntityMappingRecord,
)


class MatchingReadMixin:
    _session_factory: sessionmaker[Session]

    def lookup_mapping(
        self,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
    ) -> UUID | None:
        with self._session_factory() as session:
            mapping = self._mapping_record(
                session,
                bookmaker_id=bookmaker_id,
                entity_type=entity_type,
                source_id=source_id,
            )
            return None if mapping is None else mapping.canonical_id

    def competition_candidates(self, *, sport_id: UUID) -> tuple[CompetitionCandidate, ...]:
        with self._session_factory() as session:
            records = tuple(
                session.scalars(
                    select(CompetitionRecord).where(CompetitionRecord.sport_id == sport_id)
                )
            )
            aliases = self._competition_aliases(session, tuple(record.id for record in records))
            return tuple(
                CompetitionCandidate(
                    id=record.id,
                    sport_id=record.sport_id,
                    name=record.name,
                    country_code=record.country_code,
                    season=record.season,
                    gender=record.gender,
                    aliases=aliases.get(record.id, ()),
                )
                for record in records
            )

    def participant_candidates(self, *, sport_id: UUID) -> tuple[ParticipantCandidate, ...]:
        with self._session_factory() as session:
            records = tuple(
                session.scalars(
                    select(ParticipantRecord).where(ParticipantRecord.sport_id == sport_id)
                )
            )
            aliases = self._participant_aliases(session, tuple(record.id for record in records))
            return tuple(
                ParticipantCandidate(
                    id=record.id,
                    sport_id=record.sport_id,
                    name=record.name,
                    participant_type=record.type,
                    country_code=record.country_code,
                    aliases=aliases.get(record.id, ()),
                )
                for record in records
            )

    def event_candidates(
        self,
        *,
        sport_id: UUID,
        start_time: datetime,
        guard_window: timedelta,
    ) -> tuple[EventCandidate, ...]:
        with self._session_factory() as session:
            records = tuple(
                session.scalars(
                    select(EventRecord).where(
                        EventRecord.sport_id == sport_id,
                        EventRecord.start_time >= start_time - guard_window,
                        EventRecord.start_time <= start_time + guard_window,
                    )
                )
            )
            participants = self._event_participants(
                session,
                tuple(record.id for record in records),
            )
            return tuple(
                EventCandidate(
                    id=record.id,
                    sport_id=record.sport_id,
                    start_time=record.start_time,
                    name=record.name,
                    competition_id=record.competition_id,
                    participants=participants.get(record.id, ()),
                )
                for record in records
            )

    @staticmethod
    def _mapping_record(
        session: Session,
        *,
        bookmaker_id: UUID,
        entity_type: str,
        source_id: str,
    ) -> SourceEntityMappingRecord | None:
        return session.scalar(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.bookmaker_id == bookmaker_id,
                SourceEntityMappingRecord.entity_type == entity_type,
                SourceEntityMappingRecord.source_id == source_id,
            )
        )

    @staticmethod
    def _competition_aliases(
        session: Session,
        competition_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[str, ...]]:
        if not competition_ids:
            return {}
        grouped: defaultdict[UUID, list[str]] = defaultdict(list)
        for record in session.scalars(
            select(CompetitionAliasRecord).where(
                CompetitionAliasRecord.competition_id.in_(competition_ids)
            )
        ):
            grouped[record.competition_id].append(record.normalized_alias)
        return {key: tuple(sorted(values)) for key, values in grouped.items()}

    @staticmethod
    def _participant_aliases(
        session: Session,
        participant_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[str, ...]]:
        if not participant_ids:
            return {}
        grouped: defaultdict[UUID, list[str]] = defaultdict(list)
        for record in session.scalars(
            select(ParticipantAliasRecord).where(
                ParticipantAliasRecord.participant_id.in_(participant_ids)
            )
        ):
            grouped[record.participant_id].append(record.normalized_alias)
        return {key: tuple(sorted(values)) for key, values in grouped.items()}

    @staticmethod
    def _event_participants(
        session: Session,
        event_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[EventParticipantCandidate, ...]]:
        if not event_ids:
            return {}
        grouped: defaultdict[UUID, list[EventParticipantCandidate]] = defaultdict(list)
        for record in session.scalars(
            select(EventParticipantRecord).where(EventParticipantRecord.event_id.in_(event_ids))
        ):
            grouped[record.event_id].append(
                EventParticipantCandidate(
                    participant_id=record.participant_id,
                    role=record.role,
                    position=record.position,
                )
            )
        return {
            key: tuple(sorted(values, key=lambda item: str(item.participant_id)))
            for key, values in grouped.items()
        }
