from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from odds_aggregator.application import ConnectorIngestionService
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse
from odds_aggregator.persistence import SQLAlchemyIngestionStore, create_session_factory
from odds_aggregator.persistence.models import (
    BookmakerRecord,
    CompetitionRecord,
    EventRecord,
    MarketRecord,
    OddsQuoteRecord,
    ParticipantRecord,
    SelectionRecord,
    SourceEntityMappingRecord,
    SportRecord,
)

pytestmark = pytest.mark.integration
FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "bet365_sportradar"
SOURCE_TIME = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


def _fixture(name: str) -> dict[str, object]:
    raw: object = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


class Clock:
    def __init__(self, current: datetime) -> None:
        self.current = current

    def __call__(self) -> datetime:
        value = self.current
        self.current += timedelta(seconds=1)
        return value


class ReferenceFixtureClient:
    """Sportradar fixture client with finite, realistic schedule pagination."""

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        if path == "sports.json":
            return JsonResponse(payload=_fixture("sports.json"), headers={})
        if path.endswith("/schedules.json"):
            if "sr:sport:1" not in path:
                return JsonResponse(
                    payload={
                        "generated_at": "2026-09-09T15:00:00Z",
                        "schedules": [],
                    },
                    headers={},
                )
            start = "0" if params is None else params.get("start", "0")
            if start != "0":
                return JsonResponse(
                    payload={
                        "generated_at": "2026-09-09T15:00:00Z",
                        "schedules": [],
                    },
                    headers={},
                )
            return JsonResponse(
                payload=_fixture("schedules.json"),
                headers={"x-max-results": "2", "x-offset": "0", "x-result": "2"},
            )
        if path.endswith("/sport_event_markets.json"):
            assert "sr:sport_event:1001" in path
            return JsonResponse(payload=_fixture("markets.json"), headers={})
        raise AssertionError(f"unexpected fixture path: {path}")


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


@pytest.mark.asyncio
async def test_bet365_reference_fixture_flows_through_canonical_persistence(engine) -> None:
    session_factory = create_session_factory(engine)
    with Session(engine) as session, session.begin():
        session.add(
            BookmakerRecord(
                code="bet365",
                name="Bet365",
                enabled=True,
                created_at=SOURCE_TIME,
                updated_at=SOURCE_TIME,
            )
        )

    connector = Bet365SportradarConnector(
        client=ReferenceFixtureClient(),
        now=lambda: SOURCE_TIME,
    )
    clock = Clock(SOURCE_TIME + timedelta(hours=1))
    service = ConnectorIngestionService(SQLAlchemyIngestionStore(session_factory), now=clock)

    first = await service.ingest(
        connector,
        since=datetime(2026, 9, 10, tzinfo=UTC),
    )
    replay = await service.ingest(
        connector,
        since=datetime(2026, 9, 10, tzinfo=UTC),
    )

    assert first.sports_persisted == 2
    assert first.events_persisted == 1
    assert first.markets_persisted == 2
    assert first.selections_persisted == 5
    assert first.quotes_appended == 5
    assert replay.quotes_appended == 0

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SportRecord)) == 2
        assert session.scalar(select(func.count()).select_from(CompetitionRecord)) == 1
        assert session.scalar(select(func.count()).select_from(ParticipantRecord)) == 2
        assert session.scalar(select(func.count()).select_from(EventRecord)) == 1
        assert session.scalar(select(func.count()).select_from(MarketRecord)) == 2
        assert session.scalar(select(func.count()).select_from(SelectionRecord)) == 5
        assert session.scalar(select(func.count()).select_from(OddsQuoteRecord)) == 5

        competition = session.scalar(select(CompetitionRecord))
        assert competition is not None
        assert competition.name == "Premier League"
        participant_names = set(session.scalars(select(ParticipantRecord.name)))
        assert participant_names == {"Alpha FC", "Beta FC"}

        sport_mappings = session.scalars(
            select(SourceEntityMappingRecord)
            .where(SourceEntityMappingRecord.entity_type == "sport")
            .order_by(SourceEntityMappingRecord.source_id)
        ).all()
        assert [mapping.source_id for mapping in sport_mappings] == [
            "sr:sport:1",
            "sr:sport:2",
        ]
        assert len({mapping.canonical_id for mapping in sport_mappings}) == 2

        unavailable_count = session.scalar(
            select(func.count())
            .select_from(OddsQuoteRecord)
            .where(OddsQuoteRecord.is_available.is_(False))
        )
        assert unavailable_count == 3
