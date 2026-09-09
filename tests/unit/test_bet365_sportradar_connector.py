from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import httpx
import pytest

from odds_aggregator.connectors import (
    ConnectorHealthStatus,
    ConnectorRateLimitedError,
    ConnectorUnavailableError,
    EventFeedRequest,
    MarketFeedRequest,
    SourceMarketStatus,
)
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse, SportradarPrematchClient
from odds_aggregator.testing.connector_contract import assert_connector_contract

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "bet365_sportradar"
FIXED_NOW = datetime(2026, 9, 9, 15, 0, tzinfo=UTC)


def _fixture(name: str) -> dict[str, object]:
    raw: object = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


class FixtureClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Mapping[str, str] | None]] = []

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        self.calls.append((path, params))
        if path == "books.json":
            return JsonResponse(payload=_fixture("books.json"), headers={})
        if path == "sports.json":
            return JsonResponse(payload=_fixture("sports.json"), headers={})
        if path.endswith("/schedules.json"):
            return JsonResponse(
                payload=_fixture("schedules.json"),
                headers={"x-max-results": "3", "x-offset": "0", "x-result": "2"},
            )
        if path.endswith("/sport_event_markets.json"):
            return JsonResponse(payload=_fixture("markets.json"), headers={})
        raise AssertionError(f"unexpected fixture path: {path}")


def _connector() -> Bet365SportradarConnector:
    return Bet365SportradarConnector(client=FixtureClient(), now=lambda: FIXED_NOW)


@pytest.mark.asyncio
async def test_bet365_fixture_connector_satisfies_shared_contract() -> None:
    connector = _connector()
    await assert_connector_contract(
        connector,
        event_request=EventFeedRequest(
            sport_source_id="sr:sport:1",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        ),
        market_request=MarketFeedRequest(event_source_id="sr:sport_event:1001"),
    )


@pytest.mark.asyncio
async def test_malformed_event_is_isolated_and_pagination_is_preserved() -> None:
    connector = _connector()
    result = await connector.list_events(
        EventFeedRequest(
            sport_source_id="sr:sport:1",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        )
    )

    assert [event.source_id for event in result.events] == ["sr:sport_event:1001"]
    assert result.next_cursor == "2"
    assert result.events[0].competition_source_id == "sr:competition:17"
    assert [participant.role for participant in result.events[0].participants] == [
        "home",
        "away",
    ]


@pytest.mark.asyncio
async def test_markets_filter_to_bet365_and_keep_unavailable_prices_explicit() -> None:
    connector = _connector()
    result = await connector.get_markets(
        MarketFeedRequest(event_source_id="sr:sport_event:1001")
    )

    assert [market.source_id for market in result.markets] == [
        "b365-market-1",
        "b365-market-suspended",
    ]
    first_market = result.markets[0]
    assert first_market.status is SourceMarketStatus.OPEN
    assert first_market.metadata["bet365_external_event_id"] == "b365-event-1"
    assert first_market.metadata["skipped_outcomes"] == 1

    selections = {selection.label: selection for selection in first_market.selections}
    assert selections["home"].price.is_available is True
    assert str(selections["home"].price.decimal_odds) == "2.10"
    assert selections["draw"].price.is_available is False
    assert selections["draw"].price.decimal_odds is None
    assert selections["away"].source_id == "sr:outcome:away"

    suspended = result.markets[1]
    assert suspended.status is SourceMarketStatus.SUSPENDED
    assert all(not selection.price.is_available for selection in suspended.selections)


@pytest.mark.asyncio
async def test_health_detects_bet365_entitlement() -> None:
    connector = _connector()
    health = await connector.health()
    assert health.status is ConnectorHealthStatus.HEALTHY
    assert health.checked_at == FIXED_NOW


def test_sportradar_429_maps_retry_after_to_shared_rate_limit_error() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "7"},
        request=httpx.Request("GET", "https://api.sportradar.com/example"),
    )
    with pytest.raises(ConnectorRateLimitedError) as captured:
        SportradarPrematchClient._raise_for_status(response)
    assert captured.value.retry_after_seconds == 7.0


def test_sportradar_503_maps_to_shared_unavailable_error() -> None:
    response = httpx.Response(
        503,
        request=httpx.Request("GET", "https://api.sportradar.com/example"),
    )
    with pytest.raises(ConnectorUnavailableError):
        SportradarPrematchClient._raise_for_status(response)
