from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID


def _timestamp(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observation timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat(timespec="microseconds")


def build_observation_key(
    *,
    bookmaker_id: UUID,
    selection_id: UUID,
    decimal_odds: Decimal,
    is_available: bool,
    observed_at: datetime,
    source_updated_at: datetime | None = None,
) -> str:
    """Build a stable key for one normalized quote observation.

    Replaying identical normalized data with the same observation timestamp yields the
    same key. A changed price, availability state, selection, source timestamp, or
    observation timestamp produces a distinct historical observation.
    """
    canonical_odds = format(decimal_odds.normalize(), "f")
    payload = "|".join(
        (
            str(bookmaker_id),
            str(selection_id),
            canonical_odds,
            "1" if is_available else "0",
            _timestamp(observed_at),
            _timestamp(source_updated_at),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
