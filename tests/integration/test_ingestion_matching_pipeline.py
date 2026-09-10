from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
    SourceMarket,
    SourceParticipant,
    SourcePrice,
    SourceSelection,
    SourceSport,
)
from odds_aggregator.connectors.fake import FakeBookmakerConnector
from odds_aggregator.persistence import SQLAlchemyIngestionStore, create_session_factory
from odds_aggregator.persistence.matching_models import MatchDecisionRecord
from odds_aggregator.persistence.models import (
    BookmakerRecord,
    CompetitionRecord,
    ConnectorRunRecord,
    EventRecord,
    MarketRecord,
    OddsQuoteRecord,
    ParticipantRecord,
    SourceEntityMappingRecord,
    SportRecord,
)

pytestmark = pytest.mark.integration

BOOK_A = UUID("10000000-0000-0000-0000-00000000000a")
BOOK_B = UUID("10000000-0000-0000-0000-00000000000b")
SPORT = UUID("20000000-0000-0000-0000-000000000001")
AMBIGUOUS_A = UUID("30000000-0000-0000-0000-000000000001")
AMBIGUOUS_B = UUID("30000000-0000-0000-0000-000000000002")
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


def _seed_bookmakers(engine) -> None:
    with Session(engine) as session, session.begin():
        session.add_all(
            [
                BookmakerRecord(
                    id=BOOK_A,
                    code="fixture-a",
                    name="Fixture A",
                    enabled=True,
                    created_at=SOURCE_TIME,
                    updated_at=SOURCE_TIME,
                ),
                BookmakerRecord(
                    id=BOOK_B,
                    code="fixture-b",
                    name="Fixture B",
                    enabled=True,
                    created_at=SOURCE_TIME,
                    updated_at=SOURCE_TIME,
                ),
            ]
        )


def _connector(
    *,
    bookmaker_code: str,
    suffix: str,
    start_time: datetime,
    price: Decimal,
) -> FakeBookmakerConnector:
    sport_source_id = f"sport-{suffix}"
    competition_source_id = f"competition-{suffix}"
    home_source_id = f"inter-{suffix}"
    away_source_id = f"juventus-{suffix}"
    event_source_id = f"event-{suffix}"

    competition = SourceCompetition(
        source_id=competition_source_id,
        sport_source_id=sport_source_id,
        name="Serie A" if suffix == "a" else "SERIE-A",
        country_code="IT",
        season="2026/27",
    )
    home = SourceParticipant(
        source_id=home_source_id,
        name="Internazionale Milano" if suffix == "a" else "INTERNAZIONALE MILANO",
        participant_type="team",
    )
    away = SourceParticipant(
        source_id=away_source_id,
        name="Juventus",
        participant_type="team",
    )
    event = SourceEvent(
        source_id=event_source_id,
        sport_source_id=sport_source_id,
        competition_source_id=competition_source_id,
        competition=competition,
        name=(
            "Internazionale Milano v Juventus"
            if suffix == "a"
            else "Internazionale Milano - Juventus"
        ),
        participants=(
            SourceEventParticipant(
                source_id=home_source_id,
                role="home",
                position=1,
                participant=home,
            ),
            SourceEventParticipant(
                source_id=away_source_id,
                role="away",
                position=2,
                participant=away,
            ),
        ),
        start_time=start_time,
        source_updated_at=SOURCE_TIME,
    )
    market = SourceMarket(
        source_id=f"market-{suffix}",
        event_source_id=event_source_id,
        market_type="moneyline",
        period="full_time",
        selections=(
            SourceSelection(
                source_id=f"selection-{suffix}",
                label="Home",
                selection_type="home",
                participant_source_id=home_source_id,
                price=SourcePrice(
                    decimal_odds=price,
                    source_updated_at=SOURCE_TIME,
                ),
            ),
        ),
        source_updated_at=SOURCE_TIME,
    )
    return FakeBookmakerConnector(
        bookmaker_code=bookmaker_code,
        sports=(SourceSport(sport_source_id, "Football", code="football"),),
        events=(event,),
        markets_by_event={event_source_id: (market,)},
    )


def _mapping_id(session: Session, *, bookmaker_id: UUID, entity_type: str, source_id: str) -> UUID:
    mapping = session.scalar(
        select(SourceEntityMappingRecord).where(
            SourceEntityMappingRecord.bookmaker_id == bookmaker_id,
            SourceEntityMappingRecord.entity_type == entity_type,
            SourceEntityMappingRecord.source_id == source_id,
        )
    )
    assert mapping is not None
    return mapping.canonical_id


@pytest.mark.asyncio
async def test_two_sources_converge_through_production_ingestion(engine) -> None:
    _seed_bookmakers(engine)
    session_factory = create_session_factory(engine)
    store = SQLAlchemyIngestionStore(session_factory)
    service = ConnectorIngestionService(store, now=lambda: SOURCE_TIME + timedelta(hours=1))

    source_a = _connector(
        bookmaker_code="fixture-a",
        suffix="a",
        start_time=START,
        price=Decimal("2.10"),
    )
    source_b = _connector(
        bookmaker_code="fixture-b",
        suffix="b",
        start_time=START + timedelta(minutes=5),
        price=Decimal("2.20"),
    )

    first = await service.ingest(source_a)
    second = await service.ingest(source_b)
    replay = await service.ingest(source_b)

    assert first.events_persisted == 1
    assert second.events_persisted == 1
    assert second.events_skipped == 0
    assert replay.quotes_appended == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SportRecord)) == 1
        assert session.scalar(select(func.count()).select_from(CompetitionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ParticipantRecord)) == 2
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 1
        assert session.scalar(select(func.count()).select_from(MarketRecord)) == 2
        assert session.scalar(select(func.count()).select_from(OddsQuoteRecord)) == 2
        assert session.scalar(select(func.count()).select_from(MatchDecisionRecord)) == 8

        assert _mapping_id(
            session,
            bookmaker_id=BOOK_A,
            entity_type="competition",
            source_id="competition-a",
        ) == _mapping_id(
            session,
            bookmaker_id=BOOK_B,
            entity_type="competition",
            source_id="competition-b",
        )
        assert _mapping_id(
            session,
            bookmaker_id=BOOK_A,
            entity_type="participant",
            source_id="inter-a",
        ) == _mapping_id(
            session,
            bookmaker_id=BOOK_B,
            entity_type="participant",
            source_id="inter-b",
        )
        assert _mapping_id(
            session,
            bookmaker_id=BOOK_A,
            entity_type="event",
            source_id="event-a",
        ) == _mapping_id(
            session,
            bookmaker_id=BOOK_B,
            entity_type="event",
            source_id="event-b",
        )


def _ambiguous_connector() -> FakeBookmakerConnector:
    participant = SourceParticipant(
        source_id="ambiguous-b",
        name="United City",
        participant_type="team",
    )
    other = SourceParticipant(
        source_id="other-b",
        name="Other Team",
        participant_type="team",
    )
    event = SourceEvent(
        source_id="ambiguous-event-b",
        sport_source_id="sport-b",
        name="United City v Other Team",
        participants=(
            SourceEventParticipant(
                source_id=participant.source_id,
                role="home",
                participant=participant,
            ),
            SourceEventParticipant(
                source_id=other.source_id,
                role="away",
                participant=other,
            ),
        ),
        start_time=START,
        source_updated_at=SOURCE_TIME,
    )
    market = SourceMarket(
        source_id="must-not-fetch",
        event_source_id=event.source_id,
        market_type="moneyline",
        period="full_time",
        selections=(
            SourceSelection(
                source_id="must-not-persist",
                label="Home",
                selection_type="home",
                price=SourcePrice(decimal_odds=Decimal("2.00")),
            ),
        ),
    )
    return FakeBookmakerConnector(
        bookmaker_code="fixture-b",
        sports=(SourceSport("sport-b", "Football", code="football"),),
        events=(event,),
        markets_by_event={event.source_id: (market,)},
    )


@pytest.mark.asyncio
async def test_ambiguous_parent_skips_dependent_market_path(engine) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            BookmakerRecord(
                id=BOOK_B,
                code="fixture-b",
                name="Fixture B",
                enabled=True,
                created_at=SOURCE_TIME,
                updated_at=SOURCE_TIME,
            )
        )
        session.add(SportRecord(id=SPORT, code="football", name="Football"))
        session.add_all(
            [
                ParticipantRecord(
                    id=AMBIGUOUS_A,
                    sport_id=SPORT,
                    type="team",
                    name="United City",
                    country_code=None,
                ),
                ParticipantRecord(
                    id=AMBIGUOUS_B,
                    sport_id=SPORT,
                    type="team",
                    name="United-City",
                    country_code=None,
                ),
            ]
        )

    connector = _ambiguous_connector()
    service = ConnectorIngestionService(
        SQLAlchemyIngestionStore(create_session_factory(engine)),
        now=lambda: SOURCE_TIME + timedelta(hours=1),
    )
    result = await service.ingest(connector)

    assert result.events_persisted == 0
    assert result.events_skipped == 1
    assert result.markets_persisted == 0
    assert connector.attempts.get("get_markets", 0) == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketRecord)) == 0
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 0
        participant_mapping = session.scalar(
            select(SourceEntityMappingRecord).where(
                SourceEntityMappingRecord.bookmaker_id == BOOK_B,
                SourceEntityMappingRecord.entity_type == "participant",
                SourceEntityMappingRecord.source_id == "ambiguous-b",
            )
        )
        assert participant_mapping is None
        decision = session.scalar(
            select(MatchDecisionRecord).where(MatchDecisionRecord.source_id == "ambiguous-b")
        )
        assert decision is not None
        assert decision.state == "ambiguous"
        run = session.scalar(select(ConnectorRunRecord))
        assert run is not None
        assert run.status == "partial"
        assert run.rejected_count == 1
