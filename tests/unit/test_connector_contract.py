from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from odds_aggregator.connectors import (
    BookmakerConnector,
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


def test_connector_dtos_reject_naive_timestamps_and_missing_available_odds() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        SourceEvent(
            source_id="event-1",
            sport_source_id="sport-1",
            start_time=datetime(2026, 1, 1),
        )

    with pytest.raises(ValidationError, match="requires decimal_odds"):
        SourcePrice(is_available=True)


@pytest.mark.asyncio
async def test_fake_connector_is_deterministic_and_satisfies_protocol() -> None:
    event = SourceEvent(
        source_id="event-1",
        sport_source_id="football",
        participants=(SourceEventParticipant(source_id="team-a", role="home"),),
        start_time=datetime(2026, 9, 10, 18, 0, tzinfo=timezone.utc),
    )
    market = SourceMarket(
        source_id="m1",
        event_source_id="event-1",
        selections=(
            SourceSelection(
                source_id="s1",
                label="Home",
                price=SourcePrice(decimal_odds=Decimal("1.80")),
            ),
        ),
    )
    connector = FakeBookmakerConnector(
        sports=(SourceSport(source_id="football", name="Football"),),
        events=(event,),
        markets_by_event={"event-1": (market,)},
    )

    assert isinstance(connector, BookmakerConnector)
    assert await connector.list_sports() == [SourceSport(source_id="football", name="Football")]
    assert (await connector.list_events(EventFeedRequest(sport_source_id="football"))).events == (
        event,
    )
    assert (await connector.get_markets(MarketFeedRequest(event_source_id="event-1"))).markets == (
        market,
    )
