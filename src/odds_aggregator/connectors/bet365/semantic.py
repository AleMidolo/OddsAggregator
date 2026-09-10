"""Canonical prematch semantic translation for Sportradar Bet365 markets.

This layer deliberately wraps the mature transport/parser connector instead of
reimplementing it. Provider display text remains on DTO ``name``/``label`` fields;
only explicitly documented Sportradar market/outcome semantics become canonical
matching tokens.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import cast

from ..dtos import SourceMarket, SourceSelection
from .connector import Bet365SportradarConnector as _BaseBet365SportradarConnector


@dataclass(frozen=True, slots=True)
class _MarketSemantics:
    market_type: str
    period: str


# Sportradar Odds Comparison Prematch v2 documents market names/IDs as
# provider semantics. Only entries whose meaning maps deterministically to the
# initial prematch-v1 registry are listed here. Unknown entries remain null.
_MARKET_NAME_SEMANTICS: dict[str, _MarketSemantics] = {
    "1x2": _MarketSemantics("moneyline", "full_time"),
    "2way": _MarketSemantics("moneyline", "full_time"),
    "3way": _MarketSemantics("moneyline", "full_time"),
    "total": _MarketSemantics("total", "full_time"),
    "spread": _MarketSemantics("spread", "full_time"),
    "1x2_half_time": _MarketSemantics("moneyline", "first_half"),
}

# Current Prematch v2 overview IDs that are unambiguous for the same registry.
# Name evidence and ID evidence must agree when both are recognized.
_MARKET_ID_SEMANTICS: dict[str, _MarketSemantics] = {
    "1": _MarketSemantics("moneyline", "full_time"),
    "18": _MarketSemantics("total", "full_time"),
    "60": _MarketSemantics("moneyline", "first_half"),
}

_SELECTION_TYPES: dict[str, frozenset[str]] = {
    "moneyline": frozenset({"home", "away", "draw"}),
    "total": frozenset({"over", "under"}),
    "spread": frozenset({"home", "away"}),
}


class Bet365SportradarConnector(_BaseBet365SportradarConnector):
    """Bet365 connector with explicit prematch-v1 semantic normalization."""

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

        semantics = _resolve_market_semantics(raw_market)
        raw_outcomes = self._bet365_outcomes(raw_market)
        if semantics is not None and not _semantics_are_structurally_safe(
            semantics,
            raw_outcomes,
        ):
            semantics = None

        if semantics is None:
            return parsed.model_copy(
                update={
                    "market_type": None,
                    "period": None,
                    "scope": None,
                    "line": None,
                    "selections": tuple(
                        selection.model_copy(update={"selection_type": None})
                        for selection in parsed.selections
                    ),
                }
            )

        normalized_selections = tuple(
            _normalize_selection(selection, semantics.market_type, raw_outcomes)
            for selection in parsed.selections
        )
        market_line = _market_line(semantics.market_type, raw_outcomes)
        return parsed.model_copy(
            update={
                "market_type": semantics.market_type,
                "period": semantics.period,
                "scope": None,
                "line": market_line,
                "selections": normalized_selections,
            }
        )

    def _bet365_outcomes(
        self,
        raw_market: Mapping[str, object],
    ) -> tuple[Mapping[str, object], ...]:
        for raw_book in _object_list(raw_market.get("books")):
            if self._is_bet365_book(raw_book):
                return tuple(_object_list(raw_book.get("outcomes")))
        return ()


def _resolve_market_semantics(raw_market: Mapping[str, object]) -> _MarketSemantics | None:
    provider_name = _provider_token(raw_market.get("name"))
    by_name = _MARKET_NAME_SEMANTICS.get(provider_name) if provider_name else None
    provider_id = _provider_market_numeric_id(raw_market.get("id"))
    by_id = _MARKET_ID_SEMANTICS.get(provider_id) if provider_id else None

    if by_name is not None and by_id is not None and by_name != by_id:
        return None
    return by_id or by_name


def _semantics_are_structurally_safe(
    semantics: _MarketSemantics,
    raw_outcomes: Sequence[Mapping[str, object]],
) -> bool:
    if semantics.market_type == "moneyline":
        # A canonical moneyline has no line. Structured line-bearing outcomes
        # indicate that the provider payload is not safely represented as one.
        return not any(
            _decimal(outcome.get(field)) is not None
            for outcome in raw_outcomes
            for field in ("handicap", "spread", "total")
        )
    if semantics.market_type == "total":
        return _consistent_total(raw_outcomes) is not None
    if semantics.market_type == "spread":
        return _consistent_spread(raw_outcomes) is not None
    return False


def _normalize_selection(
    selection: SourceSelection,
    market_type: str,
    raw_outcomes: Sequence[Mapping[str, object]],
) -> SourceSelection:
    raw = _find_raw_outcome(selection, raw_outcomes)
    provider_type = _provider_token(raw.get("type")) if raw is not None else None
    if provider_type is None:
        provider_type = _provider_token(selection.selection_type)

    allowed = _SELECTION_TYPES.get(market_type, frozenset())
    selection_type = provider_type if provider_type in allowed else None

    line = selection.line
    if market_type == "moneyline":
        line = None
    elif raw is not None and market_type == "total":
        line = _decimal(raw.get("total"))
    elif raw is not None and market_type == "spread":
        line = _decimal(raw.get("spread"))

    return selection.model_copy(
        update={
            "selection_type": selection_type,
            "line": line,
        }
    )


def _find_raw_outcome(
    selection: SourceSelection,
    raw_outcomes: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    if selection.source_id is not None:
        for raw in raw_outcomes:
            raw_source_id = _string(raw.get("external_outcome_id")) or _string(raw.get("id"))
            if raw_source_id == selection.source_id:
                return raw

    provider_type = _provider_token(selection.selection_type)
    if provider_type is None:
        return None
    matches = [raw for raw in raw_outcomes if _provider_token(raw.get("type")) == provider_type]
    if len(matches) == 1:
        return matches[0]
    return None


def _market_line(
    market_type: str,
    raw_outcomes: Sequence[Mapping[str, object]],
) -> Decimal | None:
    if market_type == "total":
        return _consistent_total(raw_outcomes)
    if market_type == "spread":
        return _consistent_spread(raw_outcomes)
    return None


def _consistent_total(raw_outcomes: Sequence[Mapping[str, object]]) -> Decimal | None:
    values = [
        value
        for outcome in raw_outcomes
        if _provider_token(outcome.get("type")) in {"over", "under"}
        if (value := _decimal(outcome.get("total"))) is not None
    ]
    if not values:
        return None
    first = values[0]
    return first if all(value == first for value in values[1:]) else None


def _consistent_spread(raw_outcomes: Sequence[Mapping[str, object]]) -> Decimal | None:
    home: Decimal | None = None
    away: Decimal | None = None
    for outcome in raw_outcomes:
        outcome_type = _provider_token(outcome.get("type"))
        value = _decimal(outcome.get("spread"))
        if value is None:
            continue
        if outcome_type == "home":
            home = value
        elif outcome_type == "away":
            away = value
    if home is None or away is None or home != -away:
        return None
    return home


def _provider_token(value: object) -> str | None:
    text = _string(value)
    if text is None:
        return None
    normalized = text.casefold().replace("-", "_").replace(" ", "_")
    return "_".join(part for part in normalized.split("_") if part)


def _provider_market_numeric_id(value: object) -> str | None:
    text = _string(value)
    if text is None:
        return None
    numeric = text.rsplit(":", maxsplit=1)[-1]
    return numeric if numeric.isdigit() else None


def _object_list(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, list):
        return ()
    result: list[Mapping[str, object]] = []
    for item in cast(list[object], value):
        if isinstance(item, Mapping):
            result.append(cast(Mapping[str, object], item))
    return tuple(result)


def _string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
