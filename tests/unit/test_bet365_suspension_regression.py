from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from odds_aggregator.connectors import MarketFeedRequest, SourceMarketStatus
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse


class SuspendedMarketClient:
    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        assert path == "sport_events/sr:sport_event:1001/sport_event_markets.json"
        assert params == {"live": "false"}
        return JsonResponse(
            payload={
                "generated_at": "2026-09-09T15:00:30Z",
                "markets": [
                    {
                        "id": "sr:market:suspended-parent-only",
                        "name": "3way",
                        "books": [
                            {
                                "id": "sr:book:28901",
                                "name": "Bet365.US.NJ",
                                "external_market_id": "b365-suspended-parent-only",
                                "removed": True,
                                "outcomes": [
                                    {
                                        "id": "sr:outcome:home",
                                        "external_outcome_id": "b365-home",
                                        "type": "home",
                                        "odds_decimal": "2.10",
                                        "removed": False,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            headers={},
        )


@pytest.mark.asyncio
async def test_market_level_removal_forces_all_selections_unavailable() -> None:
    connector = Bet365SportradarConnector(
        client=SuspendedMarketClient(),
        now=lambda: datetime(2026, 9, 9, 15, 0, tzinfo=UTC),
    )

    result = await connector.get_markets(
        MarketFeedRequest(event_source_id="sr:sport_event:1001")
    )

    assert len(result.markets) == 1
    market = result.markets[0]
    assert market.status is SourceMarketStatus.SUSPENDED
    assert len(market.selections) == 1
    assert market.selections[0].price.is_available is False
    assert market.selections[0].price.decimal_odds is None
