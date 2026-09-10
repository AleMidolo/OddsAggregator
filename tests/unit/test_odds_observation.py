from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from odds_aggregator.domain.models import OddsQuote
from odds_aggregator.domain.observations import build_observation_key


def test_unavailable_quote_has_no_fabricated_price() -> None:
    observed_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
    quote = OddsQuote(
        snapshot_id=uuid4(),
        bookmaker_id=uuid4(),
        selection_id=uuid4(),
        decimal_odds=None,
        is_available=False,
        observed_at=observed_at,
        observation_key="unavailable",
    )
    assert quote.decimal_odds is None

    with pytest.raises(ValueError, match="must not carry"):
        OddsQuote(
            snapshot_id=uuid4(),
            bookmaker_id=uuid4(),
            selection_id=uuid4(),
            decimal_odds=Decimal("2.00"),
            is_available=False,
            observed_at=observed_at,
            observation_key="invalid",
        )


def test_source_timestamp_makes_retrieval_replay_idempotent() -> None:
    bookmaker_id = uuid4()
    selection_id = uuid4()
    source_updated_at = datetime(2026, 9, 9, 12, tzinfo=UTC)
    first = build_observation_key(
        bookmaker_id=bookmaker_id,
        selection_id=selection_id,
        decimal_odds=Decimal("2.10"),
        is_available=True,
        observed_at=source_updated_at + timedelta(seconds=1),
        source_updated_at=source_updated_at,
    )
    replay = build_observation_key(
        bookmaker_id=bookmaker_id,
        selection_id=selection_id,
        decimal_odds=Decimal("2.10"),
        is_available=True,
        observed_at=source_updated_at + timedelta(minutes=5),
        source_updated_at=source_updated_at,
    )
    assert first == replay
