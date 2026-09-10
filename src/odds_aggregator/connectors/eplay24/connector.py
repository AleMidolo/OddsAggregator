"""Eplay24 prematch connector using the documented OddsPapi v5 API.

The adapter consumes Eplay24 odds through a third-party API whose bookmaker
catalog explicitly includes Eplay24 IT. It never automates E-Play24 web
properties directly and intentionally rejects live/in-play fixture data.
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
    SourceCompetition,
    SourceEvent,
    SourceEventParticipant,
    SourceEventStatus,
    SourceMarket,
    SourceMarketStatus,
    SourceParticipant,
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

EPLAY24_BOOKMAKER_SLUG = "eplay24.it"
ODDSPAPI_BASE_URL = "https://v5.oddspapi.io"


@dataclass(frozen=True, slots=True)
class JsonResponse:
    payload: object
    headers: Mapping[str, str]


class OddsPapiJsonClient(Protocol):
    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse: ...


class OddsPapiClient:
    """Small async client for the documented OddsPapi v5 REST API."""

    def __init__(
        self,
        *,
        api_key: str,
        language_code: str = "en",
        timeout_seconds: float = 10.0,
    ) -> None:
        if not api_key.strip():
            raise ConnectorConfigurationError("ODDSPAPI_API_KEY must not be empty")
        language = language_code.strip().lower()
        if not language or not language.isalpha() or len(language) != 2:
            raise ConnectorConfigurationError("OddsPapi language_code must be a two-letter code")
        if timeout_seconds <= 0:
            raise ConnectorConfigurationError("timeout_seconds must be positive")

        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._base_url = f"{ODDSPAPI_BASE_URL}/{language}/"

    async def get_json(
        self,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> JsonResponse:
        request_params = dict(params or {})
        request_params["apiKey"] = self._api_key
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url,
                timeout=self._timeout_seconds,
                headers={"Accept": "application/json"},
            ) as client:
                response = await client.get(path.lstrip("/"), params=request_params)
        except httpx.TimeoutException as error:
            raise ConnectorTimeoutError("OddsPapi request timed out") from error
        except httpx.RequestError as error:
            raise ConnectorUnavailableError("OddsPapi request failed") from error

        self._raise_for_status(response)
        try:
            payload: object = response.json()
        except ValueError as error:
            raise ConnectorSchemaError("OddsPapi returned invalid JSON") from error

        headers = {key.lower(): value for key, value in response.headers.items()}
        return JsonResponse(payload=payload, headers=headers)

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status == 401:
            raise ConnectorAuthenticationError("OddsPapi rejected the API key")
        if status == 403:
            raise ConnectorAuthorizationError(
                "OddsPapi API key is not authorized for this resource"
            )
        if status == 429:
            raise ConnectorRateLimitedError(
                "OddsPapi rate limit reached",
                retry_after_seconds=_retry_after_seconds(response.headers.get("Retry-After")),
            )
        if status in {408, 504}:
            raise ConnectorTimeoutError(f"OddsPapi returned HTTP {status}")
        if status >= 500:
            raise ConnectorUnavailableError(f"OddsPapi returned HTTP {status}")
        raise ConnectorConfigurationError(f"OddsPapi returned HTTP {status}")


class Eplay24OddsPapiConnector:
    """Normalize Eplay24 prematch prices exposed by OddsPapi."""

    bookmaker_code = "eplay24"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        language_code: str = "en",
        timeout_seconds: float = 10.0,
        client: OddsPapiJsonClient | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if client is None:
            if api_key is None:
                raise ConnectorConfigurationError(
                    "api_key is required when no OddsPapi client is injected"
                )
            client = OddsPapiClient(
                api_key=api_key,
                language_code=language_code,
                timeout_seconds=timeout_seconds,
            )
        self._client = client
        self._now = now or (lambda: datetime.now(UTC))

    async def health(self) -> ConnectorHealth:
        response = await self._client.get_json(
            "bookmakers",
            params={"bookmakers": EPLAY24_BOOKMAKER_SLUG},
        )
        bookmakers = _required_object_list(response.payload, context="bookmakers")
        configured = any(
            _string(bookmaker.get("slug")) == EPLAY24_BOOKMAKER_SLUG
            and bookmaker.get("active") is True
            for bookmaker in bookmakers
        )
        if configured:
            return ConnectorHealth(
                status=ConnectorHealthStatus.HEALTHY,
                checked_at=self._now(),
                message="OddsPapi API key exposes active Eplay24 IT coverage",
            )
        return ConnectorHealth(
            status=ConnectorHealthStatus.CONFIGURATION_ERROR,
            checked_at=self._now(),
            message="OddsPapi API key does not expose active Eplay24 IT coverage",
        )

    async def list_sports(self) -> list[SourceSport]:
        response = await self._client.get_json("sports")
        sports: list[SourceSport] = []
        for raw_sport in _required_object_list(response.payload, context="sports"):
            source_id = _integer(raw_sport.get("sportId"))
            name = _string(raw_sport.get("sportName"))
            if source_id is None or name is None:
                continue
            sports.append(
                SourceSport(
                    source_id=str(source_id),
                    name=name,
                    code=None,
                    metadata={
                        "provider": "oddspapi",
                        "provider_slug": _string(raw_sport.get("slug")),
                    },
                )
            )
        return sports

    async def list_events(self, request: EventFeedRequest) -> EventFeedResult:
        if request.cursor is not None:
            raise ConnectorConfigurationError("OddsPapi fixture feed does not use cursors")
        params: dict[str, str] = {"bookmakers": EPLAY24_BOOKMAKER_SLUG}
        if request.sport_source_id is not None:
            params["sportId"] = str(_required_numeric_id(request.sport_source_id, "sport_source_id"))
        if request.competition_source_id is not None:
            params["tournamentId"] = str(
                _required_numeric_id(request.competition_source_id, "competition_source_id")
            )
        if request.sport_source_id is None and request.competition_source_id is None:
            raise ConnectorConfigurationError(
                "list_events requires sport_source_id or competition_source_id"
            )
        if request.since is not None:
            params["startTimeFrom"] = str(int(request.since.timestamp()))

        response = await self._client.get_json("fixtures", params=params)
        events: list[SourceEvent] = []
        for raw_fixture in _required_object_list(response.payload, context="fixtures"):
            event = self._parse_event(raw_fixture, request=request)
            if event is not None:
                events.append(event)
        return EventFeedResult(events=tuple(events))

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
        participants_rotated = _boolean(bookmaker_meta.get("participantsRotated"))
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
            definition = definitions.get(market_id)
            market = _parse_market(
                event_source_id=request.event_source_id,
                market_id=market_id,
                source_market_id=source_market_id,
                definition=definition,
                quotes=quotes,
                bookmaker_meta=bookmaker_meta,
                book_suspended=suspended,
                participants_rotated=participants_rotated,
                participant_ids=participant_ids,
                skipped_quotes=skipped_quotes,
            )
            if market is not None:
                markets.append(market)
        return MarketFeedResult(markets=tuple(markets))

    def _parse_event(
        self,
        raw_fixture: Mapping[str, object],
        *,
        request: EventFeedRequest,
    ) -> SourceEvent | None:
        if not _is_pregame(raw_fixture):
            return None
        source_id = _string(raw_fixture.get("fixtureId"))
        start_time = _epoch_seconds_datetime(raw_fixture.get("startTime"))
        if source_id is None or start_time is None:
            return None
        if request.since is not None and start_time < request.since:
            return None

        bookmaker_meta = _bookmaker_meta(raw_fixture)
        if bookmaker_meta is None:
            return None

        sport = _mapping(raw_fixture.get("sport"))
        tournament = _mapping(raw_fixture.get("tournament"))
        participants_raw = _mapping(raw_fixture.get("participants"))
        if sport is None or tournament is None or participants_raw is None:
            return None

        sport_id = _integer(sport.get("sportId"))
        tournament_id = _integer(tournament.get("tournamentId"))
        tournament_name = _string(tournament.get("tournamentName"))
        if sport_id is None or tournament_id is None or tournament_name is None:
            return None
        sport_source_id = str(sport_id)
        if request.sport_source_id is not None and sport_source_id != request.sport_source_id:
            return None

        competition = SourceCompetition(
            source_id=str(tournament_id),
            sport_source_id=sport_source_id,
            name=tournament_name,
            season=_season_name(raw_fixture.get("season")),
            metadata={
                "provider": "oddspapi",
                "category_name": _string(tournament.get("categoryName")),
            },
        )

        participants: list[SourceEventParticipant] = []
        participant_names: list[str] = []
        for position in (1, 2):
            participant_id = _integer(participants_raw.get(f"participant{position}Id"))
            participant_name = _string(participants_raw.get(f"participant{position}Name"))
            if participant_id is None:
                continue
            details = None
            if participant_name is not None:
                participant_names.append(participant_name)
                details = SourceParticipant(
                    source_id=str(participant_id),
                    name=participant_name,
                    participant_type=None,
                    metadata={"provider": "oddspapi"},
                )
            participants.append(
                SourceEventParticipant(
                    source_id=str(participant_id),
                    position=position,
                    participant=details,
                )
            )

        if len(participants) < 2:
            return None

        return SourceEvent(
            source_id=source_id,
            sport_source_id=sport_source_id,
            competition_source_id=str(tournament_id),
            competition=competition,
            name=" - ".join(participant_names) if len(participant_names) == 2 else None,
            participants=tuple(participants),
            start_time=start_time,
            status=SourceEventStatus.SCHEDULED,
            is_live=False,
            source_updated_at=_iso_datetime(bookmaker_meta.get("updatedAt")),
            metadata={
                "provider": "oddspapi",
                "bookmaker": EPLAY24_BOOKMAKER_SLUG,
                "bookmaker_fixture_id": _string(bookmaker_meta.get("bookmakerFixtureId")),
                "participants_rotated": _boolean(bookmaker_meta.get("participantsRotated")),
            },
        )


Quote = tuple[str, Mapping[str, object]]


def _group_quotes(
    raw_book_odds: Mapping[str, object],
) -> tuple[dict[tuple[int, str], list[Quote]], set[int], int]:
    groups: dict[tuple[int, str], list[Quote]] = {}
    market_ids: set[int] = set()
    skipped = 0
    for odds_id, raw_value in raw_book_odds.items():
        raw_quote = _mapping(raw_value)
        if raw_quote is None:
            skipped += 1
            continue
        bookmaker = _string(raw_quote.get("bookmaker"))
        market_id = _integer(raw_quote.get("marketId"))
        outcome_id = _integer(raw_quote.get("outcomeId"))
        if bookmaker != EPLAY24_BOOKMAKER_SLUG or market_id is None or outcome_id is None:
            skipped += 1
            continue
        source_market_id = _string(raw_quote.get("bookmakerMarketId")) or str(market_id)
        groups.setdefault((market_id, source_market_id), []).append((odds_id, raw_quote))
        market_ids.add(market_id)
    return groups, market_ids, skipped


def _market_definitions(payload: object) -> dict[int, Mapping[str, object]]:
    definitions: dict[int, Mapping[str, object]] = {}
    for raw_market in _required_object_list(payload, context="markets"):
        market_id = _integer(raw_market.get("marketId"))
        if market_id is not None:
            definitions[market_id] = raw_market
    return definitions


def _parse_market(
    *,
    event_source_id: str,
    market_id: int,
    source_market_id: str,
    definition: Mapping[str, object] | None,
    quotes: Sequence[Quote],
    bookmaker_meta: Mapping[str, object],
    book_suspended: bool,
    participants_rotated: bool | None,
    participant_ids: tuple[str | None, str | None],
    skipped_quotes: int,
) -> SourceMarket | None:
    outcome_names = _outcome_names(definition)
    canonical = _canonical_market(definition, participants_rotated=participants_rotated)
    market_suspended = book_suspended or any(
        quote.get("marketActive") is False for _, quote in quotes
    )
    selections: list[SourceSelection] = []
    updated_values: list[datetime] = []

    for odds_id, raw_quote in quotes:
        outcome_id = _integer(raw_quote.get("outcomeId"))
        if outcome_id is None:
            continue
        label = outcome_names.get(outcome_id) or str(outcome_id)
        selection_type = _selection_type(label) if canonical else None
        participant_source_id = _selection_participant(selection_type, participant_ids)
        active = raw_quote.get("active") is True
        market_active = raw_quote.get("marketActive") is not False
        price = _decimal(raw_quote.get("price"))
        available = (
            not market_suspended
            and active
            and market_active
            and price is not None
            and price > Decimal("1")
        )
        if not available:
            price = None

        updated_at = _epoch_millis_datetime(raw_quote.get("bookmakerChangedAt"))
        if updated_at is None:
            updated_at = _epoch_millis_datetime(raw_quote.get("changedAt"))
        if updated_at is not None:
            updated_values.append(updated_at)

        selections.append(
            SourceSelection(
                source_id=_string(raw_quote.get("bookmakerOutcomeId")) or odds_id,
                label=label,
                selection_type=selection_type,
                participant_source_id=participant_source_id,
                line=None,
                price=SourcePrice(
                    decimal_odds=price,
                    is_available=available,
                    source_updated_at=updated_at,
                ),
                metadata={
                    "provider": "oddspapi",
                    "provider_outcome_id": outcome_id,
                    "bookmaker_outcome_id": _string(raw_quote.get("bookmakerOutcomeId")),
                    "odds_id": odds_id,
                },
            )
        )

    if not selections:
        return None

    return SourceMarket(
        source_id=source_market_id,
        event_source_id=event_source_id,
        name=_string(definition.get("marketName")) if definition is not None else None,
        market_type="moneyline" if canonical else None,
        period="full_time" if canonical else None,
        scope=None,
        line=None,
        status=(
            SourceMarketStatus.SUSPENDED if market_suspended else SourceMarketStatus.OPEN
        ),
        selections=tuple(selections),
        source_updated_at=max(updated_values) if updated_values else None,
        metadata={
            "provider": "oddspapi",
            "bookmaker": EPLAY24_BOOKMAKER_SLUG,
            "provider_market_id": market_id,
            "bookmaker_market_id": (
                None if source_market_id == str(market_id) else source_market_id
            ),
            "bookmaker_fixture_id": _string(bookmaker_meta.get("bookmakerFixtureId")),
            "skipped_quotes": skipped_quotes,
        },
    )


def _canonical_market(
    definition: Mapping[str, object] | None,
    *,
    participants_rotated: bool | None,
) -> bool:
    if definition is None or participants_rotated is not False:
        return False
    market_type = _token(definition.get("marketType"))
    period = _token(definition.get("period"))
    player_prop = definition.get("playerProp")
    handicap = _decimal(definition.get("handicap"))
    return (
        market_type == "1x2"
        and period == "fulltime"
        and player_prop is not True
        and (handicap is None or handicap == Decimal("0"))
    )


def _selection_type(label: str) -> str | None:
    normalized = label.strip().casefold()
    if normalized == "1":
        return "home"
    if normalized == "x":
        return "draw"
    if normalized == "2":
        return "away"
    return None


def _selection_participant(
    selection_type: str | None,
    participant_ids: tuple[str | None, str | None],
) -> str | None:
    if selection_type == "home":
        return participant_ids[0]
    if selection_type == "away":
        return participant_ids[1]
    return None


def _participant_ids(payload: Mapping[str, object]) -> tuple[str | None, str | None]:
    participants = _mapping(payload.get("participants"))
    if participants is None:
        return (None, None)
    first = _integer(participants.get("participant1Id"))
    second = _integer(participants.get("participant2Id"))
    return (
        str(first) if first is not None else None,
        str(second) if second is not None else None,
    )


def _outcome_names(definition: Mapping[str, object] | None) -> dict[int, str]:
    if definition is None:
        return {}
    names: dict[int, str] = {}
    for raw_outcome in _object_list(definition.get("outcomes")):
        outcome_id = _integer(raw_outcome.get("outcomeId"))
        name = _string(raw_outcome.get("outcomeName"))
        if outcome_id is not None and name is not None:
            names[outcome_id] = name
    return names


def _bookmaker_meta(payload: Mapping[str, object]) -> Mapping[str, object] | None:
    bookmakers = _mapping(payload.get("bookmakers"))
    if bookmakers is None:
        return None
    meta = _mapping(bookmakers.get(EPLAY24_BOOKMAKER_SLUG))
    if meta is None or _string(meta.get("bookmaker")) != EPLAY24_BOOKMAKER_SLUG:
        return None
    return meta


def _is_pregame(payload: Mapping[str, object]) -> bool:
    status = _mapping(payload.get("status"))
    if status is None:
        return False
    return _integer(status.get("statusId")) == 0 and status.get("live") is False


def _season_name(value: object) -> str | None:
    season = _mapping(value)
    return _string(season.get("seasonName")) if season is not None else None


def _required_numeric_id(value: str, field: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ConnectorConfigurationError(f"OddsPapi {field} must be a numeric ID") from error
    if parsed < 0:
        raise ConnectorConfigurationError(f"OddsPapi {field} must be a non-negative ID")
    return parsed


def _required_object_list(payload: object, *, context: str) -> Sequence[Mapping[str, object]]:
    if not isinstance(payload, list):
        raise ConnectorSchemaError(f"OddsPapi {context} response must be an array")
    return _object_list(payload)


def _required_mapping(payload: object, *, context: str) -> Mapping[str, object]:
    mapped = _mapping(payload)
    if mapped is None:
        raise ConnectorSchemaError(f"OddsPapi {context} response must be an object")
    return mapped


def _required_mapping_field(
    payload: Mapping[str, object],
    key: str,
    *,
    context: str,
) -> Mapping[str, object]:
    mapped = _mapping(payload.get(key))
    if mapped is None:
        raise ConnectorSchemaError(f"OddsPapi {context} field '{key}' must be an object")
    return mapped


def _required_boolean(payload: Mapping[str, object], key: str, *, context: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ConnectorSchemaError(f"OddsPapi {context} field '{key}' must be a boolean")
    return value


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


def _integer(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _token(value: object) -> str | None:
    text = _string(value)
    if text is None:
        return None
    return "".join(character for character in text.casefold() if character.isalnum())


def _epoch_seconds_datetime(value: object) -> datetime | None:
    seconds = _integer(value)
    if seconds is None:
        return None
    try:
        return datetime.fromtimestamp(seconds, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _epoch_millis_datetime(value: object) -> datetime | None:
    millis = _integer(value)
    if millis is None:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None


def _iso_datetime(value: object) -> datetime | None:
    text = _string(value)
    if text is None:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


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
