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

from odds_aggregator.application import ConnectorIngestionService
from odds_aggregator.connectors import (
    SourceCompetition,
    SourceEvent,
    SourceEventParticipant,
    SourceSport,
)
from odds_aggregator.connectors.fake import FakeBookmakerConnector
from odds_aggregator.persistence import SQLAlchemyIngestionStore, create_session_factory
from odds_aggregator.persistence.matching_models import MatchDecisionRecord
from odds_aggregator.persistence.models import (
    BookmakerRecord,
    CompetitionRecord,
    EventRecord,
    ParticipantRecord,
    SourceEntityMappingRecord,
)

pytestmark = pytest.mark.integration

BOOK = UUID("10000000-0000-0000-0000-0000000000ee")
SOURCE_TIME = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
START = datetime(2026, 9, 12, 18, 0, tzinfo=UTC)


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


def _seed_bookmaker(engine) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            BookmakerRecord(
                id=BOOK,
                code="fixture-missing",
                name="Fixture Missing Evidence",
                enabled=True,
                created_at=SOURCE_TIME,
                updated_at=SOURCE_TIME,
            )
        )


def _connector(event: SourceEvent) -> FakeBookmakerConnector:
    return FakeBookmakerConnector(
        bookmaker_code="fixture-missing",
        sports=(
            SourceSport(
                source_id=event.sport_source_id,
                name="Football",
                code="football",
            ),
        ),
        events=(event,),
        markets_by_event={event.source_id: ()},
    )


@pytest.mark.asyncio
async def test_missing_competition_name_is_rejected_not_hashed(engine) -> None:
    _seed_bookmaker(engine)
    event = SourceEvent(
        source_id="event-missing-competition-evidence",
        sport_source_id="sport-missing-competition-evidence",
        competition_source_id="competition-missing-name",
        name="Fixture Event",
        start_time=START,
        source_updated_at=SOURCE_TIME,
    )
    connector = _connector(event)
    service = ConnectorIngestionService(
        SQLAlchemyIngestionStore(create_session_factory(engine)),
        now=lambda: SOURCE_TIME + timedelta(hours=1),
    )

    result = await service.ingest(connector)

    assert result.events_persisted == 0
    assert result.events_skipped == 1
    assert connector.attempts.get("get_markets", 0) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CompetitionRecord)) == 0
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 0
        mapping = session.scalar(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.bookmaker_id == BOOK,
                SourceEntityMappingRecord.entity_type == "competition",
                SourceEntityMappingRecord.source_id == "competition-missing-name",
            )
        )
        assert mapping is None
        decision = session.scalar(
            select(MatchDecisionRecord).where(
                MatchDecisionRecord.source_id == "competition-missing-name"
            )
        )
        assert decision is not None
        assert decision.state == "rejected"
        assert decision.reason_code == "invalid_name"


@pytest.mark.asyncio
async def test_missing_participant_name_is_rejected_not_hashed(engine) -> None:
    _seed_bookmaker(engine)
    competition = SourceCompetition(
        source_id="competition-with-name",
        sport_source_id="sport-missing-participant-evidence",
        name="Serie A",
    )
    event = SourceEvent(
        source_id="event-missing-participant-evidence",
        sport_source_id="sport-missing-participant-evidence",
        competition_source_id=competition.source_id,
        competition=competition,
        name="Fixture Event",
        participants=(
            SourceEventParticipant(
                source_id="participant-missing-name",
                role="home",
            ),
        ),
        start_time=START,
        source_updated_at=SOURCE_TIME,
    )
    connector = _connector(event)
    service = ConnectorIngestionService(
        SQLAlchemyIngestionStore(create_session_factory(engine)),
        now=lambda: SOURCE_TIME + timedelta(hours=1),
    )

    result = await service.ingest(connector)

    assert result.events_persisted == 0
    assert result.events_skipped == 1
    assert connector.attempts.get("get_markets", 0) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(CompetitionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ParticipantRecord)) == 0
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 0
        mapping = session.scalar(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.bookmaker_id == BOOK,
                SourceEntityMappingRecord.entity_type == "participant",
                SourceEntityMappingRecord.source_id == "participant-missing-name",
            )
        )
        assert mapping is None
        decision = session.scalar(
            select(MatchDecisionRecord).where(
                MatchDecisionRecord.source_id == "participant-missing-name"
            )
        )
        assert decision is not None
        assert decision.state == "rejected"
        assert decision.reason_code == "invalid_name"
