"""Reusable architecture-level contract checks for bookmaker connectors."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from odds_aggregator.connectors import (
    BookmakerConnector,
    ConnectorHealth,
    EventFeedRequest,
    EventFeedResult,
    MarketFeedRequest,
    MarketFeedResult,
    SourceEvent,
    SourceMarket,
    SourcePrice,
    SourceSport,
)


def _assert_aware(value: datetime) -> None:
    assert value.tzinfo is not None
    assert value.utcoffset() is not None


def _assert_source_id(value: str) -> None:
    assert value
    assert value == value.strip()


def _assert_price(price: SourcePrice) -> None:
    if price.source_updated_at is not None:
        _assert_aware(price.source_updated_at)
    if price.is_available:
        assert price.decimal_odds is not None
        assert price.decimal_odds > Decimal("1")


async def assert_connector_contract(
    connector: BookmakerConnector,
    *,
    event_request: EventFeedRequest,
    market_request: MarketFeedRequest,
) -> None:
    """Exercise the shared connector boundary against deterministic fixture data.

    Real adapters can reuse this helper by constructing the connector with sanitized,
    deterministic fixture transport and supplying requests that yield at least one event
    and market.
    """

    assert isinstance(connector, BookmakerConnector)
    bookmaker_code = connector.bookmaker_code
    assert bookmaker_code
    assert bookmaker_code == bookmaker_code.strip().lower()

    health = await connector.health()
    assert isinstance(health, ConnectorHealth)
    _assert_aware(health.checked_at)

    first_sports = await connector.list_sports()
    second_sports = await connector.list_sports()
    assert first_sports == second_sports
    assert first_sports
    assert all(isinstance(sport, SourceSport) for sport in first_sports)
    for sport in first_sports:
        _assert_source_id(sport.source_id)

    first_events = await connector.list_events(event_request)
    second_events = await connector.list_events(event_request)
    assert isinstance(first_events, EventFeedResult)
    assert first_events == second_events
    assert first_events.events
    for event in first_events.events:
        assert isinstance(event, SourceEvent)
        _assert_source_id(event.source_id)
        _assert_source_id(event.sport_source_id)
        _assert_aware(event.start_time)
        if event.source_updated_at is not None:
            _assert_aware(event.source_updated_at)
        for participant in event.participants:
            _assert_source_id(participant.source_id)

    first_markets = await connector.get_markets(market_request)
    second_markets = await connector.get_markets(market_request)
    assert isinstance(first_markets, MarketFeedResult)
    assert first_markets == second_markets
    assert first_markets.markets
    for market in first_markets.markets:
        assert isinstance(market, SourceMarket)
        _assert_source_id(market.source_id)
        _assert_source_id(market.event_source_id)
        if market.source_updated_at is not None:
            _assert_aware(market.source_updated_at)
        for selection in market.selections:
            if selection.source_id is not None:
                _assert_source_id(selection.source_id)
            _assert_price(selection.price)

    assert connector.bookmaker_code == bookmaker_code
