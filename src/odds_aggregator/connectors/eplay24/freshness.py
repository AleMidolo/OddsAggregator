"""Freshness-aware Eplay24 OddsPapi connector.

OddsPapi exposes ``staleOdds`` at bookmaker-fixture level when its connection to
the bookmaker is interrupted and current price freshness can no longer be
trusted. This wrapper keeps stale data observable while preventing it from being
persisted as currently available odds.
"""

from __future__ import annotations

from ..dtos import MarketFeedRequest, MarketFeedResult, SourceMarket, SourcePrice, SourceSelection
from ..errors import ConnectorConfigurationError, ConnectorSchemaError
from .connector import (
    EPLAY24_BOOKMAKER_SLUG,
    Eplay24OddsPapiConnector as _BaseEplay24OddsPapiConnector,
    _bookmaker_meta,
    _group_quotes,
    _is_pregame,
    _mapping,
    _market_definitions,
    _parse_market,
    _participant_ids,
    _required_boolean,
    _required_mapping,
    _required_mapping_field,
    _string,
)


class Eplay24OddsPapiConnector(_BaseEplay24OddsPapiConnector):
    """Eplay24 connector that treats provider-stale quotes as unavailable."""

    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult:
        if request.cursor is not None:
            raise ConnectorConfigurationError("OddsPapi odds feed does not use cursors")
        odds_response = await self._client.get_json(
            "fixtures/odds",
            params={
                "fixtureId": request.event_source_id,
                "bookmakers": EPLAY24_BOOKMAKER_SLUG,
            },
        )
        payload = _required_mapping(odds_response.payload, context="fixture odds")
        fixture_id = _string(payload.get("fixtureId"))
        if fixture_id is not None and fixture_id != request.event_source_id:
            raise ConnectorSchemaError("OddsPapi fixture odds response changed fixtureId")
        if not _is_pregame(payload):
            return MarketFeedResult()

        bookmaker_meta = _bookmaker_meta(payload)
        if bookmaker_meta is None:
            return MarketFeedResult()
        suspended = _required_boolean(bookmaker_meta, "suspended", context="Eplay24 fixture meta")
        stale_odds = bookmaker_meta.get("staleOdds") is True
        participants_rotated = bookmaker_meta.get("participantsRotated")
        if not isinstance(participants_rotated, bool):
            participants_rotated = None
        participant_ids = _participant_ids(payload)

        odds_root = _required_mapping_field(payload, "odds", context="fixture odds")
        raw_book_odds = _mapping(odds_root.get(EPLAY24_BOOKMAKER_SLUG))
        if raw_book_odds is None:
            return MarketFeedResult()

        groups, market_ids, skipped_quotes = _group_quotes(raw_book_odds)
        if not market_ids:
            return MarketFeedResult()

        markets_response = await self._client.get_json(
            "markets",
            params={"marketIds": ",".join(str(value) for value in sorted(market_ids))},
        )
        definitions = _market_definitions(markets_response.payload)

        markets: list[SourceMarket] = []
        for (market_id, source_market_id), quotes in groups.items():
            market = _parse_market(
                event_source_id=request.event_source_id,
                market_id=market_id,
                source_market_id=source_market_id,
                definition=definitions.get(market_id),
                quotes=quotes,
                bookmaker_meta=bookmaker_meta,
                book_suspended=suspended,
                participants_rotated=participants_rotated,
                participant_ids=participant_ids,
                skipped_quotes=skipped_quotes,
            )
            if market is not None:
                markets.append(_mark_stale_prices_unavailable(market) if stale_odds else market)
        return MarketFeedResult(markets=tuple(markets))


def _mark_stale_prices_unavailable(market: SourceMarket) -> SourceMarket:
    selections = tuple(_mark_selection_stale(selection) for selection in market.selections)
    metadata = dict(market.metadata)
    metadata["stale_odds"] = True
    return market.model_copy(update={"selections": selections, "metadata": metadata})


def _mark_selection_stale(selection: SourceSelection) -> SourceSelection:
    price = SourcePrice(
        decimal_odds=None,
        is_available=False,
        source_updated_at=selection.price.source_updated_at,
    )
    return selection.model_copy(update={"price": price})
