"""Prematch identity resolution for production connector ingestion."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from odds_aggregator.application.ingestion import (
    EventIdentityResolution,
    EventObservation,
    ResolvedEventIdentity,
)
from odds_aggregator.matching import (
    CompetitionInput,
    EventInput,
    EventParticipantInput,
    MatchOutcome,
    MatchState,
    ParticipantInput,
    PrematchMatchingService,
)

from .matching import SQLAlchemyMatchingStore
from .models import BookmakerRecord, SportRecord

_ACCEPTED_STATES = {MatchState.REUSED, MatchState.MATCHED, MatchState.CREATED}


def resolve_ingestion_event_identity(
    session_factory: sessionmaker[Session],
    *,
    bookmaker_id: UUID,
    event: EventObservation,
    observed_at: datetime,
) -> EventIdentityResolution:
    """Resolve an event graph through prematch-v1 before dependent market writes."""
    matching_store = SQLAlchemyMatchingStore(session_factory)
    sport_id = matching_store.lookup_mapping(
        bookmaker_id=bookmaker_id,
        entity_type="sport",
        source_id=event.sport_source_id,
    )
    if sport_id is None:
        raise ValueError(
            f"missing sport source mapping for '{event.sport_source_id}' before matching"
        )

    with session_factory() as session:
        bookmaker = session.get(BookmakerRecord, bookmaker_id)
        sport = session.get(SportRecord, sport_id)
        if bookmaker is None:
            raise RuntimeError(f"bookmaker {bookmaker_id} does not exist")
        if sport is None:
            raise RuntimeError("sport source mapping points to a missing canonical sport")
        bookmaker_code = bookmaker.code
        sport_code = sport.code

    matcher = PrematchMatchingService(matching_store, now=lambda: observed_at)

    # Live input is rejected before parent matching so an accidental live record cannot
    # create competition or participant identities as a side effect.
    if event.is_live or event.status.value == "live":
        outcome = matcher.resolve_event(
            bookmaker_id=bookmaker_id,
            source=_event_input(
                event,
                sport_id=sport_id,
                sport_code=sport_code,
                competition_id=None,
                participant_ids={},
            ),
        )
        return EventIdentityResolution(identity=None, reason_code=outcome.reason_code)

    competition_id: UUID | None = None
    if event.competition is not None:
        competition = event.competition
        outcome = matcher.resolve_competition(
            bookmaker_id=bookmaker_id,
            bookmaker_code=bookmaker_code,
            source=CompetitionInput(
                source_id=competition.source_id,
                sport_id=sport_id,
                name=competition.name or competition.source_id,
                country_code=competition.country_code,
                season=competition.season,
            ),
        )
        if not _accepted(outcome):
            return EventIdentityResolution(
                identity=None,
                reason_code=f"competition:{outcome.reason_code}",
            )
        competition_id = outcome.canonical_id

    participant_ids: dict[str, UUID] = {}
    for participant in event.participants:
        outcome = matcher.resolve_participant(
            bookmaker_id=bookmaker_id,
            bookmaker_code=bookmaker_code,
            source=ParticipantInput(
                source_id=participant.source_id,
                sport_id=sport_id,
                name=participant.name or participant.source_id,
                participant_type=participant.participant_type,
            ),
        )
        if not _accepted(outcome):
            return EventIdentityResolution(
                identity=None,
                reason_code=f"participant:{outcome.reason_code}",
            )
        if outcome.canonical_id is None:
            raise RuntimeError("accepted participant matching outcome has no canonical ID")
        participant_ids[participant.source_id] = outcome.canonical_id

    outcome = matcher.resolve_event(
        bookmaker_id=bookmaker_id,
        source=_event_input(
            event,
            sport_id=sport_id,
            sport_code=sport_code,
            competition_id=competition_id,
            participant_ids=participant_ids,
        ),
    )
    if not _accepted(outcome):
        return EventIdentityResolution(identity=None, reason_code=outcome.reason_code)
    if outcome.canonical_id is None:
        raise RuntimeError("accepted event matching outcome has no canonical ID")

    return EventIdentityResolution(
        identity=ResolvedEventIdentity(
            event_id=outcome.canonical_id,
            sport_id=sport_id,
            participant_ids=participant_ids,
        )
    )


def _event_input(
    event: EventObservation,
    *,
    sport_id: UUID,
    sport_code: str,
    competition_id: UUID | None,
    participant_ids: dict[str, UUID],
) -> EventInput:
    return EventInput(
        source_id=event.source_id,
        sport_id=sport_id,
        sport_code=sport_code,
        start_time=event.start_time,
        name=event.name,
        competition_source_id=(
            None if event.competition is None else event.competition.source_id
        ),
        competition_id=competition_id,
        participants=tuple(
            EventParticipantInput(
                source_id=participant.source_id,
                canonical_id=participant_ids.get(participant.source_id),
                role=participant.role,
                position=participant.position,
            )
            for participant in event.participants
        ),
        status=event.status.value,
        is_live=event.is_live,
    )


def _accepted(outcome: MatchOutcome) -> bool:
    return outcome.state in _ACCEPTED_STATES and outcome.canonical_id is not None
