from __future__ import annotations

import json
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from odds_aggregator.connectors import MarketFeedRequest
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse

FIXTURE_DIR = Path(__file__).parents[1] / "fixtures" / "bet365_sportradar"


def _fixture(name: str) -> dict[str, object]:
    raw: object = json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return cast(dict[str, object], raw)


class PayloadClient:
    def __init__(self, payload: Mapping[str, object]) -> None:
        self.payload = payload

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        del path, params
        return JsonResponse(payload=self.payload, headers={})


def _market_payload(
    *,
    market_id: str,
    name: str,
    outcomes: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "generated_at": "2026-09-09T15:00:30Z",
        "markets": [
            {
                "id": market_id,
                "name": name,
                "books": [
                    {
                        "id": "sr:book:28901",
                        "name": "Bet365.US.NJ",
                        "external_market_id": "b365-semantic-market",
                        "removed": False,
                        "outcomes": outcomes,
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_reference_fixture_emits_canonical_moneyline_and_total_semantics() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(_fixture("markets.json")))

    result = await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))

    assert len(result.markets) == 2
    moneyline, total = result.markets

    assert moneyline.name == "3way"
    assert moneyline.market_type == "moneyline"
    assert moneyline.period == "full_time"
    assert moneyline.scope is None
    assert moneyline.line is None
    assert [selection.selection_type for selection in moneyline.selections] == [
        "home",
        "draw",
        "away",
    ]
    assert all(selection.line is None for selection in moneyline.selections)

    assert total.name == "total"
    assert total.market_type == "total"
    assert total.period == "full_time"
    assert total.scope is None
    assert total.line == Decimal("2.5")
    assert [selection.selection_type for selection in total.selections] == ["over", "under"]
    assert [selection.line for selection in total.selections] == [Decimal("2.5"), Decimal("2.5")]


@pytest.mark.asyncio
async def test_documented_market_id_keeps_semantics_when_display_wording_changes() -> None:
    payload = _market_payload(
        market_id="sr:market:1",
        name="Bookmaker presentation wording",
        outcomes=[
            {"id": "home", "type": "home", "odds_decimal": "2.10"},
            {"id": "draw", "type": "draw", "odds_decimal": "3.20"},
            {"id": "away", "type": "away", "odds_decimal": "3.40"},
        ],
    )
    connector = Bet365SportradarConnector(client=PayloadClient(payload))

    market = (
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    assert market.name == "Bookmaker presentation wording"
    assert market.market_type == "moneyline"
    assert market.period == "full_time"
    assert [selection.selection_type for selection in market.selections] == [
        "home",
        "draw",
        "away",
    ]


@pytest.mark.asyncio
async def test_supported_spread_uses_structured_home_perspective_line() -> None:
    payload = _market_payload(
        market_id="sr:market:999",
        name="spread",
        outcomes=[
            {"id": "home", "type": "home", "spread": -1.5, "odds_decimal": "1.90"},
            {"id": "away", "type": "away", "spread": 1.5, "odds_decimal": "1.95"},
        ],
    )
    connector = Bet365SportradarConnector(client=PayloadClient(payload))

    market = (
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    assert market.market_type == "spread"
    assert market.period == "full_time"
    assert market.line == Decimal("-1.5")
    assert [selection.selection_type for selection in market.selections] == ["home", "away"]
    assert [selection.line for selection in market.selections] == [
        Decimal("-1.5"),
        Decimal("1.5"),
    ]


@pytest.mark.asyncio
async def test_unknown_market_preserves_display_data_but_not_canonical_tokens() -> None:
    payload = _market_payload(
        market_id="sr:market:999",
        name="Correct Score",
        outcomes=[{"id": "score", "type": "home", "odds_decimal": "5.00"}],
    )
    connector = Bet365SportradarConnector(client=PayloadClient(payload))

    market = (
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    assert market.name == "Correct Score"
    assert market.market_type is None
    assert market.period is None
    assert market.scope is None
    assert market.line is None
    assert market.selections[0].label == "home"
    assert market.selections[0].selection_type is None
    assert market.selections[0].price.decimal_odds == Decimal("5.00")


@pytest.mark.asyncio
async def test_conflicting_market_id_and_name_evidence_remains_unsupported() -> None:
    payload = _market_payload(
        market_id="sr:market:1",
        name="total",
        outcomes=[
            {"id": "over", "type": "over", "total": 2.5, "odds_decimal": "1.90"},
            {"id": "under", "type": "under", "total": 2.5, "odds_decimal": "1.90"},
        ],
    )
    connector = Bet365SportradarConnector(client=PayloadClient(payload))

    market = (
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    assert market.market_type is None
    assert market.period is None
    assert market.line is None
    assert all(selection.selection_type is None for selection in market.selections)


@pytest.mark.asyncio
async def test_inconsistent_total_threshold_is_not_promoted_to_canonical_semantics() -> None:
    payload = _market_payload(
        market_id="sr:market:999",
        name="total",
        outcomes=[
            {"id": "over", "type": "over", "total": 2.5, "odds_decimal": "1.90"},
            {"id": "under", "type": "under", "total": 2.75, "odds_decimal": "1.90"},
        ],
    )
    connector = Bet365SportradarConnector(client=PayloadClient(payload))

    market = (
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    assert market.name == "total"
    assert market.market_type is None
    assert market.period is None
    assert market.line is None
    assert all(selection.selection_type is None for selection in market.selections)


@pytest.mark.asyncio
async def test_generic_total_name_cannot_erase_documented_overtime_semantics() -> None:
    """Current-v2 ID 225 is Total (incl. overtime), not plain full-time Total."""
    payload = _market_payload(
        market_id="sr:market:225",
        name="total",
        outcomes=[
            {"id": "over", "type": "over", "total": 2.5, "odds_decimal": "1.90"},
            {"id": "under", "type": "under", "total": 2.5, "odds_decimal": "1.90"},
        ],
    )
    connector = Bet365SportradarConnector(client=PayloadClient(payload))

    market = (
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1001"))
    ).markets[0]

    # SourceMarket cannot currently express the provider's "incl. overtime"
    # variant. Until that semantic is explicitly represented, this market must
    # remain unsupported rather than collide with ordinary full-time Total.
    assert market.name == "total"
    assert market.market_type is None
    assert market.period is None
    assert market.scope is None
    assert market.line is None
    assert all(selection.selection_type is None for selection in market.selections)
