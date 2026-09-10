from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

from odds_aggregator.connectors import MarketFeedRequest
from odds_aggregator.connectors.eplay24 import Eplay24OddsPapiConnector
from odds_aggregator.connectors.eplay24.connector import JsonResponse

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "eplay24_oddspapi"


def _fixture(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


class StaleOddsFixtureClient:
    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        del params
        if path == "fixtures/odds":
            payload = _fixture("fixture_odds.json")
            assert isinstance(payload, dict)
            bookmakers = payload["bookmakers"]
            assert isinstance(bookmakers, dict)
            eplay24 = bookmakers["eplay24.it"]
            assert isinstance(eplay24, dict)
            eplay24["staleOdds"] = True
            return JsonResponse(payload=cast(dict[str, object], payload), headers={})
        if path == "markets":
            return JsonResponse(payload=_fixture("markets.json"), headers={})
        raise AssertionError(f"unexpected OddsPapi fixture path: {path}")


@pytest.mark.asyncio
async def test_stale_bookmaker_connection_cannot_expose_prices_as_available() -> None:
    connector = Eplay24OddsPapiConnector(client=StaleOddsFixtureClient())

    result = await connector.get_markets(
        MarketFeedRequest(event_source_id="op:fixture:eplay24-2001")
    )

    moneyline = next(market for market in result.markets if market.source_id == "ep24-market-1x2")
    assert moneyline.selections
    assert all(not selection.price.is_available for selection in moneyline.selections)
    assert all(selection.price.decimal_odds is None for selection in moneyline.selections)
