from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from odds_aggregator.domain import Event, EventStatus, OddsQuote, build_observation_key


def test_event_rejects_naive_start_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        Event(
            sport_id=uuid4(),
            start_time=datetime(2026, 9, 9, 12, 0),
            status=EventStatus.SCHEDULED,
            is_live=False,
        )


def test_odds_quote_requires_valid_decimal_odds() -> None:
    with pytest.raises(ValueError, match="greater than 1"):
        OddsQuote(
            snapshot_id=uuid4(),
            bookmaker_id=uuid4(),
            selection_id=uuid4(),
            decimal_odds=Decimal("1.0"),
            is_available=True,
            observed_at=datetime.now(UTC),
            observation_key="x",
        )


def test_observation_key_is_deterministic_and_sensitive_to_change() -> None:
    bookmaker_id = uuid4()
    selection_id = uuid4()
    observed_at = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)

    first = build_observation_key(
        bookmaker_id=bookmaker_id,
        selection_id=selection_id,
        decimal_odds=Decimal("2.10"),
        is_available=True,
        observed_at=observed_at,
    )
    replay = build_observation_key(
        bookmaker_id=bookmaker_id,
        selection_id=selection_id,
        decimal_odds=Decimal("2.100"),
        is_available=True,
        observed_at=observed_at,
    )
    changed = build_observation_key(
        bookmaker_id=bookmaker_id,
        selection_id=selection_id,
        decimal_odds=Decimal("2.20"),
        is_available=True,
        observed_at=observed_at,
    )

    assert first == replay
    assert first != changed


def test_domain_layer_has_no_framework_or_adapter_imports() -> None:
    domain_root = Path(__file__).parents[2] / "src" / "odds_aggregator" / "domain"
    forbidden = ("sqlalchemy", "fastapi", "odds_aggregator.connectors")
    for path in domain_root.glob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, f"{token} leaked into {path.name}"
