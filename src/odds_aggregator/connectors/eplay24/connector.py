"""Eplay24 prematch adapter using licensed Sportradar Odds Comparison access.

E-Play24 publicly states that it uses Betradar/Sportradar for pre-match odds. This
adapter therefore uses the documented Sportradar Odds Comparison Prematch API and
never automates E-Play24 web properties directly.

The public Sportradar documentation does not publish a stable E-Play24 book ID.
The connector consequently validates the configured Books entitlement at runtime
and optionally accepts the exact book ID returned for the operator's API key.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from ..bet365.connector import SportradarJsonClient
from ..bet365.semantic import Bet365SportradarConnector as _SportradarSemanticConnector
from ..dtos import ConnectorHealth, ConnectorHealthStatus, EventFeedRequest, SourceEvent, SourceMarket
from ..errors import ConnectorConfigurationError

EPLAY24_BOOK_NAME = "E-Play24"
_UNCONFIGURED_BOOK_ID = "sr:book:eplay24-unconfigured"


class Eplay24SportradarConnector(_SportradarSemanticConnector):
    """Normalize Eplay24 prices exposed through an entitled Sportradar OC feed."""

    bookmaker_code = "eplay24"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        access_level: str = "production",
        language_code: str = "en",
        timeout_seconds: float = 10.0,
        client: SportradarJsonClient | None = None,
        now: Callable[[], datetime] | None = None,
        eplay24_book_id: str | None = None,
        eplay24_book_name: str = EPLAY24_BOOK_NAME,
    ) -> None:
        book_name = eplay24_book_name.strip()
        if not book_name:
            raise ConnectorConfigurationError("eplay24_book_name must not be empty")

        book_id = eplay24_book_id.strip() if eplay24_book_id is not None else None
        if book_id == "":
            raise ConnectorConfigurationError("eplay24_book_id must not be empty when provided")

        self._eplay24_book_id = book_id
        self._eplay24_book_name = book_name
        super().__init__(
            api_key=api_key,
            access_level=access_level,
            language_code=language_code,
            timeout_seconds=timeout_seconds,
            client=client,
            now=now,
            bet365_book_id=book_id or _UNCONFIGURED_BOOK_ID,
            bet365_book_name=book_name,
        )

    async def health(self) -> ConnectorHealth:
        """Verify that this API key's Books feed exposes Eplay24."""

        health = await super().health()
        if health.status is ConnectorHealthStatus.HEALTHY:
            message = f"Sportradar entitlement includes {self._eplay24_book_name}"
        else:
            identity = self._eplay24_book_id or self._eplay24_book_name
            message = (
                "Sportradar API key does not expose the configured Eplay24 book "
                f"({identity}); enable the required Odds Comparison Core/book entitlement"
            )
        return health.model_copy(update={"message": message})

    def _is_bet365_book(self, raw_book: Mapping[str, object]) -> bool:
        """Override the mature base hook with Eplay24 book identity matching.

        When an exact book ID has been configured from the caller's Books feed it
        is authoritative. Without an ID, compare a punctuation-insensitive brand
        name so documented variants such as ``E-Play24`` and ``Eplay24`` match.
        """

        source_id = _string(raw_book.get("id"))
        if self._eplay24_book_id is not None:
            return source_id == self._eplay24_book_id

        name = _string(raw_book.get("name"))
        return name is not None and _book_name_key(name) == _book_name_key(self._eplay24_book_name)

    def _parse_event(
        self,
        raw_event: Mapping[str, object],
        *,
        request: EventFeedRequest,
        generated_at: datetime | None,
    ) -> SourceEvent | None:
        parsed = super()._parse_event(raw_event, request=request, generated_at=generated_at)
        if parsed is None:
            return None
        metadata = dict(parsed.metadata)
        metadata["bookmaker"] = self.bookmaker_code
        return parsed.model_copy(update={"metadata": metadata})

    def _parse_market(
        self,
        raw_market: Mapping[str, object],
        *,
        event_source_id: str,
        generated_at: datetime | None,
    ) -> SourceMarket | None:
        parsed = super()._parse_market(
            raw_market,
            event_source_id=event_source_id,
            generated_at=generated_at,
        )
        if parsed is None:
            return None

        metadata = dict(parsed.metadata)
        external_market_id = metadata.pop("bet365_external_market_id", None)
        external_event_id = metadata.pop("bet365_external_event_id", None)
        metadata["bookmaker"] = self.bookmaker_code
        metadata["eplay24_external_market_id"] = external_market_id
        metadata["eplay24_external_event_id"] = external_event_id
        return parsed.model_copy(update={"metadata": metadata})


def _book_name_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None
