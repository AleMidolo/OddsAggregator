"""Bet365 odds adapter using Sportradar Odds Comparison Prematch v2.

The adapter never accesses Bet365 web properties directly. Bet365 currently prohibits
screen-scraping/automated extraction in its customer terms, so this connector consumes
only a separately licensed Sportradar API entitlement that includes Bet365.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from typing import Protocol, cast

import httpx

from ..dtos import (
    ConnectorHealth,
    ConnectorHealthStatus,
    EventFeedRequest,
    EventFeedResult,
    MarketFeedRequest,
    MarketFeedResult,
    SourceEvent,
    SourceEventParticipant,
    SourceEventStatus,
    SourceMarket,
    SourceMarketStatus,
    SourcePrice,
    SourceSelection,
    SourceSport,
)
from ..errors import (
    ConnectorAuthenticationError,
    ConnectorAuthorizationError,
    ConnectorConfigurationError,
    ConnectorRateLimitedError,
    ConnectorSchemaError,
    ConnectorTimeoutError,
    ConnectorUnavailableError,
)

BET365_BOOK_ID = "sr:book:28901"
BET365_BOOK_NAME = "Bet365.US.NJ"
PAGE_SIZE = 50


@dataclass(frozen=True, slots=True)
class JsonResponse:
    payload: Mapping[str, object]
    headers: Mapping[str, str]


class SportradarJsonClient(Protocol):
    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse: ...


class SportradarPrematchClient:
    """Small async HTTP client for Sportradar Odds Comparison Prematch v2."""

    def __init__(
        self,
        *,
        api_key: str,
        access_level: str = "trial",
        language_code: str = "en",
        timeout_seconds: float = 10.0,
    ) -> None:
        if not api_key.strip():
            raise ConnectorConfigurationError("SPORTRADAR_API_KEY must not be empty")
        if access_level not in {"trial", "production"}:
            raise ConnectorConfigurationError(
                "Sportradar access_level must be 'trial' or 'production'"
            )
        if timeout_seconds <= 0:
            raise ConnectorConfigurationError("timeout_seconds must be positive")

        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._base_url = (
            "https://api.sportradar.com/oddscomparison-prematch/"
            f"{access_level}/v2/{language_code}/"
        )

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                headers={"x-api-key": self._api_key, "Accept": "application/json"},
            ) as client:
                response = await client.get(path.lstrip("/"), params=params)
        except httpx.TimeoutException as error:
            raise ConnectorTimeoutError("Sportradar request timed out") from error
        except httpx.RequestError as error:
            raise ConnectorUnavailableError("Sportradar request failed") from error

        self._raise_for_status(response)
        try:
            raw_payload: object = response.json()
        except ValueError as error:
            raise ConnectorSchemaError("Sportradar returned invalid JSON") from error

        if not isinstance(raw_payload, dict):
            raise ConnectorSchemaError("Sportradar JSON response must be an object")

        payload = cast(dict[str, object], raw_payload)
        headers = {key.lower(): value for key, value in response.headers.items()}
        return JsonResponse(payload=payload, headers=headers)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 401:
            raise ConnectorAuthenticationError("Sportradar rejected the API key")
        if status == 403:
            raise ConnectorAuthorizationError(
                "Sportradar API key is not authorized for this resource"
            )
        if status == 429:
            raise ConnectorRateLimitedError(
                "Sportradar rate limit reached",
                retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if status in {408, 504}:
            raise ConnectorTimeoutError(f"Sportradar returned HTTP {status}")
        if status >= 500:
            raise ConnectorUnavailableError(f"Sportradar returned HTTP {status}")
        raise ConnectorConfigurationError(f"Sportradar returned HTTP {status}")


class Bet365SportradarConnector:
    """Normalize Bet365 prices exposed by a licensed Sportradar feed."""

    bookmaker_code = "bet365"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        access_level: str = "trial",
        language_code: str = "en",
        timeout_seconds: float = 10.0,
        client: SportradarJsonClient | None = None,
        now: Callable[[], datetime] | None = None,
        bet365_book_id: str = BET365_BOOK_ID,
        bet365_book_name: str = BET365_BOOK_NAME,
    ) -> None:
        if client is None:
            if api_key is None:
                raise ConnectorConfigurationError(
                    "api_key is required when no Sportradar client is injected"
                )
            client = SportradarPrematchClient(
                api_key=api_key,
                access_level=access_level,
                language_code=language_code,
                timeout_seconds=timeout_seconds,
            )
        self._client = client
        self._now = now or (lambda: datetime.now(UTC))
        self._book_id = bet365_book_id
        self._book_name = bet365_book_name

    async def health(self) -> ConnectorHealth:
        response = await self._client.get_json("books.json")
        configured = any(self._is_bet365_book(book) for book in _object_list(response.payload.get("books")))
        if configured:
            return ConnectorHealth(
                status=ConnectorHealthStatus.HEALTHY,
                checked_at=self._now(),
                message=f"Sportradar entitlement includes {self._book_name}",
            )
        return ConnectorHealth(
            status=ConnectorHealthStatus.CONFIGURATION_ERROR,
            checked_at=self._now(),
            message=(
                "Sportradar API key does not expose the configured Bet365 book; "
                "request the required bookmaker entitlement"
            ),
        )

    async def list_sports(self) -> list[SourceSport]:
        response = await self._client.get_json("sports.json")
        sports: list[SourceSport] = []
        for raw_sport in _object_list(response.payload.get("sports")):
            source_id = _string(raw_sport.get("id"))
            name = _string(raw_sport.get("name"))
            if source_id is None or name is None:
                continue
            sports.append(
                SourceSport(
                    source_id=source_id,
                    name=name,
                    code=_string(raw_sport.get("type")),
                    metadata={"provider": "sportradar", "book": self._book_name},
                )
            )
        return sports

    async def list_events(self, request: EventFeedRequest) -> EventFeedResult:
        offset = _cursor_offset(request.cursor)
        params = {"start": str(offset), "limit": str(PAGE_SIZE)}
        if request.competition_source_id is not None:
            path = f"competitions/{request.competition_source_id}/schedules.json"
        elif request.sport_source_id is not None:
            day = (request.since or self._now()).date().isoformat()
            path = f"sports/{request.sport_source_id}/schedules/{day}/schedules.json"
            params["live"] = "false"
        else:
            raise ConnectorConfigurationError(
                "list_events requires sport_source_id or competition_source_id"
            )

        response = await self._client.get_json(path, params=params)
        generated_at = _aware_datetime(response.payload.get("generated_at"))
        raw_schedules = _object_list(response.payload.get("schedules"))
        if not raw_schedules:
            raw_schedules = _object_list(response.payload.get("sport_events"))

        events: list[SourceEvent] = []
        for raw_schedule in raw_schedules:
            raw_event = _mapping(raw_schedule.get("sport_event")) or raw_schedule
            event = self._parse_event(raw_event, request=request, generated_at=generated_at)
            if event is not None:
                events.append(event)

        next_cursor = _next_cursor(
            response.headers,
            current_offset=offset,
            returned=len(raw_schedules),
        )
        return EventFeedResult(events=tuple(events), next_cursor=next_cursor)

    async def get_markets(self, request: MarketFeedRequest) -> MarketFeedResult:
        response = await self._client.get_json(
            f"sport_events/{request.event_source_id}/sport_event_markets.json",
            params={"live": "false"},
        )
        generated_at = _aware_datetime(response.payload.get("generated_at"))
        markets: list[SourceMarket] = []
        for raw_market in _object_list(response.payload.get("markets")):
            market = self._parse_market(
                raw_market,
                event_source_id=request.event_source_id,
                generated_at=generated_at,
            )
            if market is not None:
                markets.append(market)
        return MarketFeedResult(markets=tuple(markets))

    def _parse_event(
        self,
        raw_event: Mapping[str, object],
        *,
        request: EventFeedRequest,
        generated_at: datetime | None,
    ) -> SourceEvent | None:
        source_id = _string(raw_event.get("id"))
        start_time = _aware_datetime(raw_event.get("start_time"))
        if start_time is None:
            start_time = _aware_datetime(raw_event.get("scheduled"))
        if source_id is None or start_time is None:
            return None
        if request.since is not None and start_time < request.since:
            return None

        context = _mapping(raw_event.get("sport_event_context")) or {}
        sport = _mapping(context.get("sport")) or _mapping(raw_event.get("sport")) or {}
        competition = (
            _mapping(context.get("competition"))
            or _mapping(raw_event.get("competition"))
            or _mapping(raw_event.get("tournament"))
            or {}
        )
        sport_source_id = _string(sport.get("id")) or request.sport_source_id
        if sport_source_id is None:
            return None
        competition_source_id = _string(competition.get("id")) or request.competition_source_id

        participants: list[SourceEventParticipant] = []
        competitor_names: list[str] = []
        for raw_competitor in _object_list(raw_event.get("competitors")):
            competitor_id = _string(raw_competitor.get("id"))
            if competitor_id is None:
                continue
            competitor_names.append(_string(raw_competitor.get("name")) or competitor_id)
            participants.append(
                SourceEventParticipant(
                    source_id=competitor_id,
                    role=_string(raw_competitor.get("qualifier")),
                )
            )

        raw_status = _string(raw_event.get("status")) or "unknown"
        status = _event_status(raw_status)
        name = _string(raw_event.get("name"))
        if name is None and competitor_names:
            name = " - ".join(competitor_names)

        return SourceEvent(
            source_id=source_id,
            sport_source_id=sport_source_id,
            competition_source_id=competition_source_id,
            name=name,
            participants=tuple(participants),
            start_time=start_time,
            status=status,
            is_live=status is SourceEventStatus.LIVE,
            source_updated_at=generated_at,
            metadata={
                "provider": "sportradar",
                "book": self._book_name,
                "source_status": raw_status,
            },
        )

    def _parse_market(
        self,
        raw_market: Mapping[str, object],
        *,
        event_source_id: str,
        generated_at: datetime | None,
    ) -> SourceMarket | None:
        bet365_book: Mapping[str, object] | None = None
        for raw_book in _object_list(raw_market.get("books")):
            if self._is_bet365_book(raw_book):
                bet365_book = raw_book
                break
        if bet365_book is None:
            return None

        provider_market_id = _string(raw_market.get("id"))
        external_market_id = _string(bet365_book.get("external_market_id"))
        source_id = external_market_id or provider_market_id
        if source_id is None:
            return None

        removed = _boolean(bet365_book.get("removed"), default=False)
        selections: list[SourceSelection] = []
        skipped_outcomes = 0
        for raw_outcome in _object_list(bet365_book.get("outcomes")):
            selection = _parse_selection(raw_outcome, generated_at=generated_at)
            if selection is None:
                skipped_outcomes += 1
                continue
            selections.append(selection)

        if not selections and not removed:
            return None

        status = SourceMarketStatus.SUSPENDED if removed else SourceMarketStatus.OPEN
        return SourceMarket(
            source_id=source_id,
            event_source_id=event_source_id,
            name=_string(raw_market.get("name")),
            market_type=_string(raw_market.get("name")),
            status=status,
            selections=tuple(selections),
            source_updated_at=generated_at,
            metadata={
                "provider": "sportradar",
                "book_id": _string(bet365_book.get("id")) or self._book_id,
                "book_name": _string(bet365_book.get("name")) or self._book_name,
                "provider_market_id": provider_market_id,
                "bet365_external_market_id": external_market_id,
                "bet365_external_event_id": _string(
                    bet365_book.get("external_sport_event_id")
                ),
                "skipped_outcomes": skipped_outcomes,
            },
        )

    def _is_bet365_book(self, raw_book: Mapping[str, object]) -> bool:
        source_id = _string(raw_book.get("id"))
        name = _string(raw_book.get("name"))
        if source_id is not None and _book_numeric_id(source_id) == _book_numeric_id(self._book_id):
            return True
        return name is not None and name.casefold() == self._book_name.casefold()


def _parse_selection(
    raw_outcome: Mapping[str, object],
    *,
    generated_at: datetime | None,
) -> SourceSelection | None:
    removed = _boolean(raw_outcome.get("removed"), default=False)
    decimal_odds = _decimal(raw_outcome.get("odds_decimal"))
    available = not removed and decimal_odds is not None and decimal_odds > Decimal("1")
    if not available:
        decimal_odds = None

    label = (
        _string(raw_outcome.get("type"))
        or _string(raw_outcome.get("player_name"))
        or _string(raw_outcome.get("external_outcome_id"))
        or _string(raw_outcome.get("id"))
    )
    if label is None:
        return None

    source_id = _string(raw_outcome.get("external_outcome_id")) or _string(raw_outcome.get("id"))
    line = _decimal(raw_outcome.get("handicap"))
    if line is None:
        line = _decimal(raw_outcome.get("spread"))
    if line is None:
        line = _decimal(raw_outcome.get("total"))

    return SourceSelection(
        source_id=source_id,
        label=label,
        selection_type=_string(raw_outcome.get("type")),
        line=line,
        price=SourcePrice(
            decimal_odds=decimal_odds,
            is_available=available,
            source_updated_at=generated_at,
        ),
        metadata={
            "provider_outcome_id": _string(raw_outcome.get("id")),
            "bet365_external_outcome_id": _string(raw_outcome.get("external_outcome_id")),
        },
    )


def _retry_after_seconds(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
    return max(0.0, seconds)


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return cast(Mapping[str, object], value)


def _object_list(value: object) -> Sequence[Mapping[str, object]]:
    if not isinstance(value, list):
        return ()
    result: list[Mapping[str, object]] = []
    for item in cast(list[object], value):
        mapped = _mapping(item)
        if mapped is not None:
            result.append(mapped)
    return result


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _boolean(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return default


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _aware_datetime(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        offset = int(cursor)
    except ValueError as error:
        raise ConnectorConfigurationError("event cursor must be a non-negative integer") from error
    if offset < 0:
        raise ConnectorConfigurationError("event cursor must be a non-negative integer")
    return offset


def _next_cursor(
    headers: Mapping[str, str],
    *,
    current_offset: int,
    returned: int,
) -> str | None:
    maximum = _integer(headers.get("x-max-results"))
    offset = _integer(headers.get("x-offset"))
    result_count = _integer(headers.get("x-result"))
    effective_offset = current_offset if offset is None else offset
    effective_result = returned if result_count is None else result_count
    if maximum is None or effective_result <= 0:
        return None
    next_offset = effective_offset + effective_result
    if next_offset >= maximum:
        return None
    return str(next_offset)


def _integer(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _book_numeric_id(value: str) -> str:
    return value.rsplit(":", maxsplit=1)[-1]


def _event_status(value: str) -> SourceEventStatus:
    normalized = value.strip().lower()
    if normalized in {"not_started", "scheduled"}:
        return SourceEventStatus.SCHEDULED
    if normalized in {
        "live",
        "1st_half",
        "2nd_half",
        "halftime",
        "overtime",
        "awaiting_penalties",
        "penalties",
        "in_progress",
    }:
        return SourceEventStatus.LIVE
    if normalized in {"ended", "closed", "finished"}:
        return SourceEventStatus.FINISHED
    if normalized in {"cancelled", "canceled"}:
        return SourceEventStatus.CANCELLED
    if normalized in {"postponed", "delayed"}:
        return SourceEventStatus.POSTPONED
    if normalized in {"suspended", "interrupted"}:
        return SourceEventStatus.SUSPENDED
    return SourceEventStatus.UNKNOWN
