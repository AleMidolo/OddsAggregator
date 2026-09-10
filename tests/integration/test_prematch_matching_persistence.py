from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from odds_aggregator.domain.canonical_ids import canonical_entity_id
from odds_aggregator.matching import (
    CompetitionInput,
    EventInput,
    EventParticipantInput,
    MatchState,
    ParticipantInput,
    PrematchMatchingService,
)
from odds_aggregator.persistence import SQLAlchemyMatchingStore, create_session_factory
from odds_aggregator.persistence.matching_models import MatchCandidateRecord, MatchDecisionRecord
from odds_aggregator.persistence.models import (
    BookmakerRecord,
    CompetitionAliasRecord,
    CompetitionRecord,
    EventParticipantRecord,
    EventRecord,
    ParticipantAliasRecord,
    ParticipantRecord,
    SourceEntityMappingRecord,
    SportRecord,
)

pytestmark = pytest.mark.integration

BOOKMAKER_ID = UUID("10000000-0000-0000-0000-000000000001")
SPORT_ID = UUID("20000000-0000-0000-0000-000000000001")
COMPETITION_ID = UUID("30000000-0000-0000-0000-000000000001")
HOME_ID = UUID("40000000-0000-0000-0000-000000000001")
AWAY_ID = UUID("40000000-0000-0000-0000-000000000002")
EVENT_ID = UUID("50000000-0000-0000-0000-000000000001")
START = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)
NOW = datetime(2026, 9, 10, 10, 0, tzinfo=UTC)


@pytest.fixture()
def engine():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    database_engine = create_engine(url)
    try:
        yield database_engine
    finally:
        database_engine.dispose()


def _seed_reference_graph(engine) -> None:
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                BookmakerRecord(
                    id=BOOKMAKER_ID,
                    code="book-b",
                    name="Book B",
                    enabled=True,
                    created_at=NOW,
                    updated_at=NOW,
                ),
                SportRecord(id=SPORT_ID, code="football", name="Football"),
            ]
        )
        session.flush()
        session.add(
            CompetitionRecord(
                id=COMPETITION_ID,
                sport_id=SPORT_ID,
                name="Serie A",
                country_code="IT",
                gender=None,
                season="2026-2027",
            )
        )
        session.add_all(
            [
                ParticipantRecord(
                    id=HOME_ID,
                    sport_id=SPORT_ID,
                    type="team",
                    name="Internazionale Milano",
                    country_code=None,
                ),
                ParticipantRecord(
                    id=AWAY_ID,
                    sport_id=SPORT_ID,
                    type="team",
                    name="Juventus",
                    country_code=None,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                CompetitionAliasRecord(
                    competition_id=COMPETITION_ID,
                    normalized_alias="serie a",
                    source="canonical",
                ),
                ParticipantAliasRecord(
                    participant_id=HOME_ID,
                    normalized_alias="inter",
                    source="validated",
                ),
            ]
        )
        session.add(
            EventRecord(
                id=EVENT_ID,
                sport_id=SPORT_ID,
                competition_id=COMPETITION_ID,
                name="Internazionale Milano v Juventus",
                start_time=START,
                status="scheduled",
                is_live=False,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.flush()
        session.add_all(
            [
                EventParticipantRecord(
                    event_id=EVENT_ID,
                    participant_id=HOME_ID,
                    role="home",
                    position=1,
                ),
                EventParticipantRecord(
                    event_id=EVENT_ID,
                    participant_id=AWAY_ID,
                    role="away",
                    position=2,
                ),
            ]
        )


def test_competition_participant_event_matching_replay_and_audit(engine) -> None:
    _seed_reference_graph(engine)
    service = PrematchMatchingService(
        SQLAlchemyMatchingStore(create_session_factory(engine)),
        now=lambda: NOW,
    )

    competition = service.resolve_competition(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=CompetitionInput(
            source_id="competition-b",
            sport_id=SPORT_ID,
            name="SERIE-A",
            country_code="it",
            season="2026/27",
        ),
    )
    home = service.resolve_participant(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=ParticipantInput("home-b", SPORT_ID, "Inter", "team"),
    )
    away = service.resolve_participant(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=ParticipantInput("away-b", SPORT_ID, "Juventus", "team"),
    )
    event_source = EventInput(
        source_id="event-b",
        sport_id=SPORT_ID,
        sport_code="football",
        start_time=START + timedelta(minutes=5),
        name="Internazionale Milano - Juventus",
        competition_source_id="competition-b",
        competition_id=COMPETITION_ID,
        participants=(
            EventParticipantInput("home-b", HOME_ID, role="home", position=1),
            EventParticipantInput("away-b", AWAY_ID, role="away", position=2),
        ),
    )
    event = service.resolve_event(bookmaker_id=BOOKMAKER_ID, source=event_source)

    assert competition.state is MatchState.MATCHED
    assert competition.canonical_id == COMPETITION_ID
    assert home.state is MatchState.MATCHED
    assert home.canonical_id == HOME_ID
    assert away.state is MatchState.MATCHED
    assert away.canonical_id == AWAY_ID
    assert event.state is MatchState.MATCHED
    assert event.canonical_id == EVENT_ID

    replay = service.resolve_event(bookmaker_id=BOOKMAKER_ID, source=event_source)
    assert replay.state is MatchState.REUSED
    assert replay.canonical_id == EVENT_ID

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MatchDecisionRecord)) == 4
        assert session.scalar(select(func.count()).select_from(SourceEntityMappingRecord)) == 4
        assert session.scalar(select(func.count()).select_from(MatchCandidateRecord)) >= 4


def test_nonaccepted_replay_and_created_identity_are_safe(engine) -> None:
    _seed_reference_graph(engine)
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                ParticipantRecord(
                    id=UUID("40000000-0000-0000-0000-000000000010"),
                    sport_id=SPORT_ID,
                    type="team",
                    name="United City",
                    country_code=None,
                ),
                ParticipantRecord(
                    id=UUID("40000000-0000-0000-0000-000000000011"),
                    sport_id=SPORT_ID,
                    type="team",
                    name="United-City",
                    country_code=None,
                ),
            ]
        )

    service = PrematchMatchingService(
        SQLAlchemyMatchingStore(create_session_factory(engine)),
        now=lambda: NOW,
    )
    ambiguous_source = ParticipantInput("ambiguous", SPORT_ID, "United City", "team")
    ambiguous = service.resolve_participant(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=ambiguous_source,
    )
    ambiguous_replay = service.resolve_participant(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=ambiguous_source,
    )
    assert ambiguous.state is MatchState.AMBIGUOUS
    assert ambiguous.decision_id == ambiguous_replay.decision_id

    unresolved = service.resolve_event(
        bookmaker_id=BOOKMAKER_ID,
        source=EventInput(
            source_id="unresolved-event",
            sport_id=SPORT_ID,
            sport_code="football",
            start_time=START,
            name="Unknown",
            participants=(
                EventParticipantInput("home-b", HOME_ID),
                EventParticipantInput("missing", None),
            ),
        ),
    )
    live = service.resolve_event(
        bookmaker_id=BOOKMAKER_ID,
        source=EventInput(
            source_id="live-event",
            sport_id=SPORT_ID,
            sport_code="football",
            start_time=START,
            is_live=True,
            participants=(
                EventParticipantInput("home-b", HOME_ID),
                EventParticipantInput("away-b", AWAY_ID),
            ),
        ),
    )
    created_source = ParticipantInput("new-club", SPORT_ID, "Completely New Club", "team")
    created = service.resolve_participant(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=created_source,
    )
    created_replay = service.resolve_participant(
        bookmaker_id=BOOKMAKER_ID,
        bookmaker_code="book-b",
        source=created_source,
    )

    assert unresolved.state is MatchState.UNRESOLVED
    assert live.state is MatchState.REJECTED
    assert live.reason_code == "out_of_scope_live"
    assert created.state is MatchState.CREATED
    assert created.canonical_id == canonical_entity_id(
        BOOKMAKER_ID,
        "participant",
        "new-club",
    )
    assert created_replay.state is MatchState.REUSED

    with Session(engine) as session:
        mapped_sources = set(
            session.scalars(
                select(SourceEntityMappingRecord.source_id).where(
                    SourceEntityMappingRecord.bookmaker_id == BOOKMAKER_ID
                )
            )
        )
        assert "ambiguous" not in mapped_sources
        assert "unresolved-event" not in mapped_sources
        assert "live-event" not in mapped_sources
        assert "new-club" in mapped_sources
        ambiguous_decisions = session.scalar(
            select(func.count()).select_from(MatchDecisionRecord).where(
                MatchDecisionRecord.source_id == "ambiguous"
            )
        )
        assert ambiguous_decisions == 1
