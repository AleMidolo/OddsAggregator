from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
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
from odds_aggregator.connectors.eplay24 import Eplay24SportradarConnector
from odds_aggregator.matching.normalization import normalize_name
from odds_aggregator.testing.connector_contract import assert_connector_contract

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures"
EPLAY24_FIXTURES = FIXTURE_ROOT / "eplay24_sportradar"
BET365_FIXTURES = FIXTURE_ROOT / "bet365_sportradar"
FIXED_NOW = datetime(2026, 9, 10, 17, 15, tzinfo=UTC)


def _fixture(directory: Path, name: str) -> dict[str, object]:
    raw: object = json.loads((directory / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


class FixtureClient:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.calls: list[tuple[str, Mapping[str, str] | None]] = []

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        self.calls.append((path, params))
        if path == "books.json":
            return JsonResponse(payload=_fixture(self.directory, "books.json"), headers={})
        if path == "sports.json":
            return JsonResponse(payload=_fixture(self.directory, "sports.json"), headers={})
        if path.endswith("/schedules.json"):
            return JsonResponse(
                payload=_fixture(self.directory, "schedules.json"),
                headers={"x-max-results": "2", "x-offset": "0", "x-result": "2"},
            )
        if path.endswith("/sport_event_markets.json"):
            return JsonResponse(payload=_fixture(self.directory, "markets.json"), headers={})
        raise AssertionError(f"unexpected fixture path: {path}")


def _eplay24_connector(*, book_id: str | None = "sr:book:999999") -> Eplay24SportradarConnector:
    return Eplay24SportradarConnector(
        client=FixtureClient(EPLAY24_FIXTURES),
        now=lambda: FIXED_NOW,
        eplay24_book_id=book_id,
    )


@pytest.mark.asyncio
async def test_eplay24_fixture_connector_satisfies_shared_contract() -> None:
    connector = _eplay24_connector()
    await assert_connector_contract(
        connector,
        event_request=EventFeedRequest(
            sport_source_id="sr:sport:eplay24-soccer",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        ),
        market_request=MarketFeedRequest(event_source_id="sr:sport_event:eplay24-2001"),
    )
    assert connector.bookmaker_code == "eplay24"


@pytest.mark.asyncio
async def test_health_validates_configured_books_entitlement() -> None:
    connector = _eplay24_connector()
    health = await connector.health()

    assert health.status is ConnectorHealthStatus.HEALTHY
    assert health.checked_at == FIXED_NOW
    assert "E-Play24" in (health.message or "")


@pytest.mark.asyncio
async def test_health_can_match_documented_brand_name_when_book_id_not_configured() -> None:
    connector = _eplay24_connector(book_id=None)
    health = await connector.health()

    assert health.status is ConnectorHealthStatus.HEALTHY


@pytest.mark.asyncio
async def test_explicit_book_id_is_authoritative_for_entitlement() -> None:
    connector = _eplay24_connector(book_id="sr:book:not-entitled")
    health = await connector.health()

    assert health.status is ConnectorHealthStatus.CONFIGURATION_ERROR
    assert "Odds Comparison Core" in (health.message or "")


@pytest.mark.asyncio
async def test_market_filtering_preserves_eplay24_identity_and_semantics() -> None:
    connector = _eplay24_connector()
    result = await connector.get_markets(
        MarketFeedRequest(event_source_id="sr:sport_event:eplay24-2001")
    )

    assert [market.source_id for market in result.markets] == [
        "ep24-market-1",
        "ep24-market-total-suspended",
    ]

    moneyline = result.markets[0]
    assert moneyline.market_type == "moneyline"
    assert moneyline.period == "full_time"
    assert [selection.selection_type for selection in moneyline.selections] == [
        "home",
        "draw",
        "away",
    ]
    assert moneyline.metadata["bookmaker"] == "eplay24"
    assert moneyline.metadata["eplay24_external_event_id"] == "ep24-event-771"
    assert moneyline.metadata["skipped_outcomes"] == 1
    assert "bet365_external_market_id" not in moneyline.metadata
    assert "bet365_external_event_id" not in moneyline.metadata

    suspended_total = result.markets[1]
    assert suspended_total.status is SourceMarketStatus.SUSPENDED
    assert suspended_total.market_type == "total"
    assert suspended_total.period == "full_time"
    assert str(suspended_total.line) == "2.5"
    assert all(not selection.price.is_available for selection in suspended_total.selections)


@pytest.mark.asyncio
async def test_fixture_is_ready_for_cross_source_reconciliation_without_id_equality() -> None:
    eplay24 = _eplay24_connector()
    bet365 = Bet365SportradarConnector(
        client=FixtureClient(BET365_FIXTURES),
        now=lambda: FIXED_NOW,
    )

    eplay_event = (
        await eplay24.list_events(
            EventFeedRequest(
                sport_source_id="sr:sport:eplay24-soccer",
                since=datetime(2026, 9, 10, tzinfo=UTC),
            )
        )
    ).events[0]
    bet365_event = (
        await bet365.list_events(
            EventFeedRequest(
                sport_source_id="sr:sport:1",
                since=datetime(2026, 9, 10, tzinfo=UTC),
            )
        )
    ).events[0]

    assert eplay_event.source_id != bet365_event.source_id
    assert eplay_event.competition_source_id != bet365_event.competition_source_id
    assert [participant.source_id for participant in eplay_event.participants] != [
        participant.source_id for participant in bet365_event.participants
    ]
    assert eplay_event.name != bet365_event.name
    assert abs(eplay_event.start_time - bet365_event.start_time) == timedelta(minutes=2)

    eplay_names = [
        participant.participant.name
        for participant in eplay_event.participants
        if participant.participant is not None
    ]
    bet365_names = [
        participant.participant.name
        for participant in bet365_event.participants
        if participant.participant is not None
    ]
    assert eplay_names != bet365_names
    assert [normalize_name(name) for name in eplay_names] == [
        normalize_name(name) for name in bet365_names
    ]

    eplay_market = (
        await eplay24.get_markets(
            MarketFeedRequest(event_source_id="sr:sport_event:eplay24-2001")
        )
    ).markets[0]
    bet365_market = (
        await bet365.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    assert eplay_market.source_id != bet365_market.source_id
    assert eplay_market.market_type == bet365_market.market_type == "moneyline"
    assert eplay_market.period == bet365_market.period == "full_time"
    assert [selection.selection_type for selection in eplay_market.selections] == [
        "home",
        "draw",
        "away",
    ]


def test_sportradar_rate_limit_error_is_shared_by_eplay24_transport() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "9"},
        request=httpx.Request("GET", "https://api.sportradar.com/example"),
    )
    with pytest.raises(ConnectorRateLimitedError) as captured:
        SportradarPrematchClient._raise_for_status(response)
    assert captured.value.retry_after_seconds == 9.0


def test_sportradar_temporary_failure_is_shared_by_eplay24_transport() -> None:
    response = httpx.Response(
        503,
        request=httpx.Request("GET", "https://api.sportradar.com/example"),
    )
    with pytest.raises(ConnectorUnavailableError):
        SportradarPrematchClient._raise_for_status(response)
