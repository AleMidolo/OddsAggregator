from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import httpx
import pytest

from odds_aggregator.connectors import (
    ConnectorAuthenticationError,
    ConnectorAuthorizationError,
    ConnectorHealthStatus,
    ConnectorRateLimitedError,
    ConnectorSchemaError,
    ConnectorUnavailableError,
    EventFeedRequest,
    MarketFeedRequest,
    SourceMarketStatus,
)
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse as SportradarJsonResponse
from odds_aggregator.connectors.eplay24 import Eplay24OddsPapiConnector, OddsPapiClient
from odds_aggregator.connectors.eplay24.connector import JsonResponse as OddsPapiJsonResponse
from odds_aggregator.matching.normalization import normalize_name
from odds_aggregator.testing.connector_contract import assert_connector_contract

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures"
EPLAY24_FIXTURES = FIXTURE_ROOT / "eplay24_oddspapi"
BET365_FIXTURES = FIXTURE_ROOT / "bet365_sportradar"
FIXED_NOW = datetime(2026, 9, 10, 17, 30, tzinfo=UTC)


def _fixture(directory: Path, name: str) -> object:
    return json.loads((directory / name).read_text(encoding="utf-8"))


class OddsPapiFixtureClient:
    def __init__(self, *, bookmaker_payload: object | None = None) -> None:
        self.bookmaker_payload = bookmaker_payload
        self.calls: list[tuple[str, Mapping[str, str] | None]] = []

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> OddsPapiJsonResponse:
        self.calls.append((path, params))
        if path == "bookmakers":
            payload = (
                self.bookmaker_payload
                if self.bookmaker_payload is not None
                else _fixture(EPLAY24_FIXTURES, "bookmakers.json")
            )
        elif path == "sports":
            payload = _fixture(EPLAY24_FIXTURES, "sports.json")
        elif path == "fixtures":
            payload = _fixture(EPLAY24_FIXTURES, "fixtures.json")
        elif path == "fixtures/odds":
            payload = _fixture(EPLAY24_FIXTURES, "fixture_odds.json")
        elif path == "markets":
            payload = _fixture(EPLAY24_FIXTURES, "markets.json")
        else:
            raise AssertionError(f"unexpected OddsPapi fixture path: {path}")
        return OddsPapiJsonResponse(payload=payload, headers={})


class SportradarFixtureClient:
    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> SportradarJsonResponse:
        del params
        if path == "books.json":
            name = "books.json"
        elif path == "sports.json":
            name = "sports.json"
        elif path.endswith("/schedules.json"):
            name = "schedules.json"
        elif path.endswith("/sport_event_markets.json"):
            name = "markets.json"
        else:
            raise AssertionError(f"unexpected Sportradar fixture path: {path}")
        payload = _fixture(BET365_FIXTURES, name)
        assert isinstance(payload, dict)
        return SportradarJsonResponse(payload=cast(dict[str, object], payload), headers={})


def _connector(*, client: OddsPapiFixtureClient | None = None) -> Eplay24OddsPapiConnector:
    return Eplay24OddsPapiConnector(
        client=client or OddsPapiFixtureClient(),
        now=lambda: FIXED_NOW,
    )


@pytest.mark.asyncio
async def test_eplay24_fixture_connector_satisfies_shared_contract() -> None:
    connector = _connector()
    await assert_connector_contract(
        connector,
        event_request=EventFeedRequest(
            sport_source_id="10",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        ),
        market_request=MarketFeedRequest(event_source_id="op:fixture:eplay24-2001"),
    )
    assert connector.bookmaker_code == "eplay24"


@pytest.mark.asyncio
async def test_health_requires_active_eplay24_coverage() -> None:
    healthy = await _connector().health()
    assert healthy.status is ConnectorHealthStatus.HEALTHY
    assert healthy.checked_at == FIXED_NOW

    missing_client = OddsPapiFixtureClient(
        bookmaker_payload=[
            {"slug": "eplay24.it", "bookmakerName": "Eplay24 IT", "active": False}
        ]
    )
    missing = await _connector(client=missing_client).health()
    assert missing.status is ConnectorHealthStatus.CONFIGURATION_ERROR


@pytest.mark.asyncio
async def test_list_events_filters_live_and_malformed_siblings() -> None:
    client = OddsPapiFixtureClient()
    connector = _connector(client=client)

    result = await connector.list_events(
        EventFeedRequest(
            sport_source_id="10",
            since=datetime(2026, 9, 10, tzinfo=UTC),
        )
    )

    assert len(result.events) == 1
    event = result.events[0]
    assert event.source_id == "op:fixture:eplay24-2001"
    assert event.status.value == "scheduled"
    assert event.is_live is False
    assert event.competition is not None
    assert event.competition.name == "Premier League"
    assert [participant.source_id for participant in event.participants] == ["90110", "90120"]
    assert [participant.position for participant in event.participants] == [1, 2]
    assert all(participant.role is None for participant in event.participants)
    assert event.metadata["bookmaker_fixture_id"] == "ep24-fixture-771"

    path, params = next(call for call in client.calls if call[0] == "fixtures")
    assert path == "fixtures"
    assert params is not None
    assert params["bookmakers"] == "eplay24.it"
    assert params["sportId"] == "10"
    assert "startTimeFrom" in params


@pytest.mark.asyncio
async def test_markets_filter_eplay24_and_preserve_state_and_native_ids() -> None:
    connector = _connector()
    result = await connector.get_markets(
        MarketFeedRequest(event_source_id="op:fixture:eplay24-2001")
    )

    assert [market.source_id for market in result.markets] == [
        "ep24-market-1x2",
        "ep24-market-total",
    ]

    moneyline = result.markets[0]
    assert moneyline.name == "Full Time Result"
    assert moneyline.market_type == "moneyline"
    assert moneyline.period == "full_time"
    assert moneyline.line is None
    assert moneyline.status is SourceMarketStatus.OPEN
    assert [selection.source_id for selection in moneyline.selections] == [
        "ep24-home",
        "ep24-draw",
        "ep24-away",
    ]
    assert [selection.selection_type for selection in moneyline.selections] == [
        "home",
        "draw",
        "away",
    ]
    assert [selection.participant_source_id for selection in moneyline.selections] == [
        "90110",
        None,
        "90120",
    ]
    assert [str(selection.price.decimal_odds) for selection in moneyline.selections] == [
        "2.08",
        "3.36",
        "3.29",
    ]
    assert moneyline.metadata["provider"] == "oddspapi"
    assert moneyline.metadata["bookmaker_fixture_id"] == "ep24-fixture-771"
    assert moneyline.metadata["skipped_quotes"] == 1

    suspended = result.markets[1]
    assert suspended.status is SourceMarketStatus.SUSPENDED
    assert suspended.market_type is None
    assert suspended.period is None
    assert all(not selection.price.is_available for selection in suspended.selections)
    assert all(selection.price.decimal_odds is None for selection in suspended.selections)


@pytest.mark.asyncio
async def test_fixture_is_matchable_against_bet365_without_shared_source_ids() -> None:
    eplay24 = _connector()
    bet365 = Bet365SportradarConnector(
        client=SportradarFixtureClient(),
        now=lambda: FIXED_NOW,
    )

    eplay_event = (
        await eplay24.list_events(
            EventFeedRequest(
                sport_source_id="10",
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
    assert [participant.source_id for participant in eplay_event.participants] != [
        participant.source_id for participant in bet365_event.participants
    ]

    eplay_market = (
        await eplay24.get_markets(
            MarketFeedRequest(event_source_id="op:fixture:eplay24-2001")
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


@pytest.mark.asyncio
async def test_structurally_invalid_feed_root_is_rejected() -> None:
    client = OddsPapiFixtureClient(bookmaker_payload={"bookmakers": []})
    with pytest.raises(ConnectorSchemaError):
        await _connector(client=client).health()


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (401, ConnectorAuthenticationError),
        (403, ConnectorAuthorizationError),
        (503, ConnectorUnavailableError),
    ],
)
def test_http_errors_map_to_shared_taxonomy(
    status: int,
    error_type: type[Exception],
) -> None:
    response = httpx.Response(
        status,
        request=httpx.Request("GET", "https://v5.oddspapi.io/en/bookmakers"),
    )
    with pytest.raises(error_type):
        OddsPapiClient._raise_for_status(response)


def test_rate_limit_preserves_retry_after() -> None:
    response = httpx.Response(
        429,
        headers={"Retry-After": "1.5"},
        request=httpx.Request("GET", "https://v5.oddspapi.io/en/fixtures/odds"),
    )
    with pytest.raises(ConnectorRateLimitedError) as captured:
        OddsPapiClient._raise_for_status(response)
    assert captured.value.retry_after_seconds == 1.5
