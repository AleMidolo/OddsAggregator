from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from odds_aggregator.domain import OddsQuote, SourceEntityMapping, SourceEntityType, build_observation_key
from odds_aggregator.persistence.models import (
    BookmakerRecord,
    ConnectorRunRecord,
    EventRecord,
    MarketRecord,
    MarketSnapshotRecord,
    OddsQuoteRecord,
    SelectionRecord,
    SportRecord,
)
from odds_aggregator.persistence.repositories import (
    SQLAlchemyHistoricalOddsRepository,
    SQLAlchemySourceMappingRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture()
def session() -> Session:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is not configured")

    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    engine = create_engine(url)
    with Session(engine) as session:
        yield session
        session.rollback()
    engine.dispose()


def _seed_quote_graph(session: Session):
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    bookmaker_id, sport_id, event_id = uuid4(), uuid4(), uuid4()
    market_id, selection_id, run_id, snapshot_id = uuid4(), uuid4(), uuid4(), uuid4()
    session.add_all(
        [
            BookmakerRecord(id=bookmaker_id, code="fixture", name="Fixture", enabled=True, created_at=now, updated_at=now),
            SportRecord(id=sport_id, code="football", name="Football"),
            EventRecord(id=event_id, sport_id=sport_id, competition_id=None, name="A v B", start_time=now, status="scheduled", is_live=False, created_at=now, updated_at=now),
            MarketRecord(id=market_id, event_id=event_id, market_type="moneyline", period="full_time", line=None, scope=None, variant=None, created_at=now, updated_at=now),
            SelectionRecord(id=selection_id, market_id=market_id, selection_type="home", participant_id=None, line=None, name="A"),
            ConnectorRunRecord(id=run_id, bookmaker_id=bookmaker_id, operation="fixture", scope=None, started_at=now, finished_at=None, status="running", attempt_count=0, received_count=0, accepted_count=0, rejected_count=0, error_code=None, error_summary=None),
            MarketSnapshotRecord(id=snapshot_id, bookmaker_id=bookmaker_id, market_id=market_id, run_id=run_id, observed_at=now, source_updated_at=None, is_live=False, market_status="open"),
        ]
    )
    session.flush()
    return now, bookmaker_id, sport_id, selection_id, snapshot_id


def test_source_mapping_uniqueness_and_reuse(session: Session) -> None:
    now, bookmaker_id, sport_id, _, _ = _seed_quote_graph(session)
    repo = SQLAlchemySourceMappingRepository(session)
    mapping = SourceEntityMapping(
        bookmaker_id=bookmaker_id,
        entity_type=SourceEntityType.SPORT,
        source_id="src-football",
        canonical_id=sport_id,
        first_seen_at=now,
        last_seen_at=now,
    )
    first = repo.upsert(mapping)
    replay = repo.upsert(mapping)

    assert first.id == replay.id
    assert repo.get(bookmaker_id=bookmaker_id, entity_type=SourceEntityType.SPORT, source_id="src-football") is not None


def test_quote_replay_is_idempotent_and_distinct_change_is_append_only(session: Session) -> None:
    now, bookmaker_id, _, selection_id, snapshot_id = _seed_quote_graph(session)
    repo = SQLAlchemyHistoricalOddsRepository(session)

    key = build_observation_key(bookmaker_id=bookmaker_id, selection_id=selection_id, decimal_odds=Decimal("2.10"), is_available=True, observed_at=now)
    quote = OddsQuote(snapshot_id=snapshot_id, bookmaker_id=bookmaker_id, selection_id=selection_id, decimal_odds=Decimal("2.10"), is_available=True, observed_at=now, observation_key=key)
    assert repo.append(quote) is True
    assert repo.append(quote) is False

    changed_key = build_observation_key(bookmaker_id=bookmaker_id, selection_id=selection_id, decimal_odds=Decimal("2.20"), is_available=True, observed_at=now)
    changed = OddsQuote(snapshot_id=snapshot_id, bookmaker_id=bookmaker_id, selection_id=selection_id, decimal_odds=Decimal("2.20"), is_available=True, observed_at=now, observation_key=changed_key)
    assert repo.append(changed) is True

    count = session.scalar(select(func.count()).select_from(OddsQuoteRecord))
    assert count == 2
