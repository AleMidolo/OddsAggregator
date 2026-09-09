from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pytest

from odds_aggregator.connectors import (
    ConnectorSchemaError,
    EventFeedRequest,
    MarketFeedRequest,
)
from odds_aggregator.connectors.bet365 import Bet365SportradarConnector
from odds_aggregator.connectors.bet365.connector import JsonResponse


@dataclass(slots=True)
class PayloadClient:
    payload: Mapping[str, object]

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        return JsonResponse(payload=self.payload, headers={})


@pytest.mark.asyncio
async def test_list_sports_rejects_missing_required_root() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(payload={}))

    with pytest.raises(ConnectorSchemaError, match="missing 'sports'"):
        await connector.list_sports()


@pytest.mark.asyncio
async def test_list_sports_rejects_wrong_type_required_root() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(payload={"sports": {}}))

    with pytest.raises(ConnectorSchemaError, match="'sports' must be an array"):
        await connector.list_sports()


@pytest.mark.asyncio
async def test_list_events_rejects_missing_required_root() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(payload={}))

    with pytest.raises(ConnectorSchemaError, match="missing 'schedules' or 'sport_events'"):
        await connector.list_events(EventFeedRequest(sport_source_id="sr:sport:1"))


@pytest.mark.asyncio
async def test_list_events_rejects_wrong_type_required_root() -> None:
    connector = Bet365SportradarConnector(
        client=PayloadClient(payload={"schedules": {"unexpected": "object"}})
    )

    with pytest.raises(ConnectorSchemaError, match="'schedules' must be an array"):
        await connector.list_events(EventFeedRequest(sport_source_id="sr:sport:1"))


@pytest.mark.asyncio
async def test_list_events_accepts_empty_required_array() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(payload={"schedules": []}))

    result = await connector.list_events(EventFeedRequest(sport_source_id="sr:sport:1"))

    assert result.events == ()
    assert result.next_cursor is None


@pytest.mark.asyncio
async def test_get_markets_rejects_missing_required_root() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(payload={}))

    with pytest.raises(ConnectorSchemaError, match="missing 'markets'"):
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1"))


@pytest.mark.asyncio
async def test_get_markets_rejects_wrong_type_required_root() -> None:
    connector = Bet365SportradarConnector(client=PayloadClient(payload={"markets": None}))

    with pytest.raises(ConnectorSchemaError, match="'markets' must be an array"):
        await connector.get_markets(MarketFeedRequest(event_source_id="sr:sport_event:1"))
