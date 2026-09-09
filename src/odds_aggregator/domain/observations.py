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
    decimal_odds: Decimal | None,
    is_available: bool,
    observed_at: datetime,
    source_updated_at: datetime | None = None,
) -> str:
    """Build a stable key for one normalized quote/state observation.

    When a source update timestamp exists it is the replay identity timestamp, so
    re-fetching the same provider observation later remains idempotent. Otherwise the
    retrieval timestamp identifies the observation. Availability without a price is
    represented explicitly rather than inventing a decimal odds value.
    """
    canonical_odds = "" if decimal_odds is None else format(decimal_odds.normalize(), "f")
    identity_timestamp = source_updated_at or observed_at
    payload = "|".join(
        (
            str(bookmaker_id),
            str(selection_id),
            canonical_odds,
            "1" if is_available else "0",
            _timestamp(identity_timestamp),
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
