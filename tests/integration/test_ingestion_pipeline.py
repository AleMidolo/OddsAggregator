from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from odds_aggregator.application import ConnectorIngestionService
from odds_aggregator.connectors import (
    SourceEvent,
    SourceEventParticipant,
    SourceMarket,
    SourceMarketStatus,
    SourcePrice,
    SourceSelection,
    SourceSport,
)
from odds_aggregator.connectors.fake import FakeBookmakerConnector
from odds_aggregator.persistence import SQLAlchemyIngestionStore, create_session_factory
from odds_aggregator.persistence.models import (
    BookmakerRecord,
    ConnectorRunRecord,
    EventParticipantRecord,
    EventRecord,
    MarketRecord,
    MarketSnapshotRecord,
    OddsQuoteRecord,
    ParticipantRecord,
    SelectionRecord,
    SourceEntityMappingRecord,
    SportRecord,
)

pytestmark = pytest.mark.integration
SOURCE_TIME = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


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
    yield database_engine
    database_engine.dispose()


def _connector(price: Decimal) -> FakeBookmakerConnector:
    event = SourceEvent(
        source_id="event-1",
        sport_source_id="sport-football",
        competition_source_id="competition-1",
        name="Alpha v Beta",
        participants=(
            SourceEventParticipant(source_id="team-alpha", role="home", position=1),
            SourceEventParticipant(source_id="team-beta", role="away", position=2),
        ),
        start_time=datetime(2026, 9, 10, 18, 0, tzinfo=UTC),
        source_updated_at=SOURCE_TIME,
    )
    open_market = SourceMarket(
        source_id="market-open",
        event_source_id=event.source_id,
        market_type="moneyline",
        period="full_time",
        status=SourceMarketStatus.OPEN,
        source_updated_at=SOURCE_TIME,
        selections=(
            SourceSelection(
                source_id="selection-home",
                label="Alpha",
                selection_type="home",
                participant_source_id="team-alpha",
                price=SourcePrice(
                    decimal_odds=price,
                    is_available=True,
                    source_updated_at=SOURCE_TIME,
                ),
            ),
        ),
    )
    suspended_market = SourceMarket(
        source_id="market-suspended",
        event_source_id=event.source_id,
        market_type="total",
        period="full_time",
        status=SourceMarketStatus.SUSPENDED,
        source_updated_at=SOURCE_TIME,
        selections=(
            SourceSelection(
                source_id="selection-over",
                label="Over",
                selection_type="over",
                price=SourcePrice(
                    decimal_odds=None,
                    is_available=False,
                    source_updated_at=SOURCE_TIME,
                ),
            ),
        ),
    )
    return FakeBookmakerConnector(
        bookmaker_code="fixture",
        sports=(SourceSport(source_id="sport-football", name="Football", code="football"),),
        events=(event,),
        markets_by_event={event.source_id: (open_market, suspended_market)},
    )


@pytest.mark.asyncio
async def test_fixture_ingestion_is_idempotent_append_only_and_preserves_unavailable(
    engine,
) -> None:
    session_factory = create_session_factory(engine)
    with Session(engine) as session, session.begin():
        session.add(
            BookmakerRecord(
                code="fixture",
                name="Fixture Bookmaker",
                enabled=True,
                created_at=SOURCE_TIME,
                updated_at=SOURCE_TIME,
            )
        )

    clock = Clock(SOURCE_TIME + timedelta(hours=1))
    service = ConnectorIngestionService(SQLAlchemyIngestionStore(session_factory), now=clock)
    first = await service.ingest(_connector(Decimal("2.10")))
    replay = await service.ingest(_connector(Decimal("2.10")))
    changed = await service.ingest(_connector(Decimal("2.20")))

    assert first.quotes_appended == 2
    assert replay.quotes_appended == 0
    assert changed.quotes_appended == 1

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SportRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ParticipantRecord)) == 2
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 1
        assert session.scalar(select(func.count()).select_from(EventParticipantRecord)) == 2
        assert session.scalar(select(func.count()).select_from(MarketRecord)) == 2
        assert session.scalar(select(func.count()).select_from(SelectionRecord)) == 2
        assert session.scalar(select(func.count()).select_from(SourceEntityMappingRecord)) == 9
        assert session.scalar(select(func.count()).select_from(MarketSnapshotRecord)) == 3
        assert session.scalar(select(func.count()).select_from(OddsQuoteRecord)) == 3
        assert session.scalar(select(func.count()).select_from(ConnectorRunRecord)) == 3

        unavailable = session.scalar(
            select(OddsQuoteRecord).where(OddsQuoteRecord.is_available.is_(False))
        )
        assert unavailable is not None
        assert unavailable.decimal_odds is None
