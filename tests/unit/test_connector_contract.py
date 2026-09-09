from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from odds_aggregator.connectors import (
    EventFeedRequest,
    MarketFeedRequest,
    SourceEvent,
    SourceEventParticipant,
    SourceMarket,
    SourceMarketStatus,
    SourcePrice,
    SourceSelection,
    SourceSport,
)
from odds_aggregator.connectors.fake import FakeBookmakerConnector
from tests.contract_harness import assert_connector_contract


def test_connector_dtos_preserve_source_identity_and_explicit_suspension() -> None:
    market = SourceMarket(
        source_id="market-7",
        event_source_id="event-3",
        status=SourceMarketStatus.SUSPENDED,
        selections=(
            SourceSelection(
                source_id="selection-9",
                label="Home",
                price=SourcePrice(decimal_odds=Decimal("2.15"), is_available=False),
            ),
        ),
    )

    assert market.source_id == "market-7"
    assert market.status is SourceMarketStatus.SUSPENDED
    assert market.selections[0].source_id == "selection-9"
    assert market.selections[0].price.decimal_odds == Decimal("2.15")
    assert market.selections[0].price.is_available is False


def test_connector_dtos_reject_malformed_timestamps_and_prices() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        SourceEvent(
            source_id="event-1",
            sport_source_id="sport-1",
            start_time=datetime(2026, 1, 1),
        )

    with pytest.raises(ValidationError, match="requires decimal_odds"):
        SourcePrice(is_available=True)

    with pytest.raises(ValidationError, match="greater than 1"):
        SourcePrice(decimal_odds=Decimal("1.0"), is_available=True)


def test_optional_source_fields_may_be_absent() -> None:
    sport = SourceSport(source_id="football", name="Football")
    event = SourceEvent(
        source_id="event-1",
        sport_source_id=sport.source_id,
        start_time=datetime(2026, 9, 10, 18, 0, tzinfo=UTC),
    )
    market = SourceMarket(
        source_id="market-1",
        event_source_id=event.source_id,
        selections=(
            SourceSelection(
                label="Unavailable",
                price=SourcePrice(is_available=False),
            ),
        ),
    )

    assert sport.code is None
    assert event.competition_source_id is None
    assert event.name is None
    assert market.name is None
    assert market.selections[0].source_id is None
    assert market.selections[0].price.decimal_odds is None


@pytest.mark.asyncio
async def test_fake_connector_passes_reusable_connector_contract() -> None:
    event = SourceEvent(
        source_id="event-1",
        sport_source_id="football",
        participants=(SourceEventParticipant(source_id="team-a", role="home"),),
        start_time=datetime(2026, 9, 10, 18, 0, tzinfo=UTC),
    )
    market = SourceMarket(
        source_id="m1",
        event_source_id="event-1",
        status=SourceMarketStatus.SUSPENDED,
        selections=(
            SourceSelection(
                source_id="s1",
                label="Home",
                price=SourcePrice(decimal_odds=Decimal("1.80"), is_available=False),
            ),
        ),
    )
    connector = FakeBookmakerConnector(
        bookmaker_code="fake",
        sports=(SourceSport(source_id="football", name="Football"),),
        events=(event,),
        markets_by_event={"event-1": (market,)},
    )

    await assert_connector_contract(
        connector,
        event_request=EventFeedRequest(sport_source_id="football"),
        market_request=MarketFeedRequest(event_source_id="event-1"),
    )
