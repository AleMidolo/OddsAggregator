"""Deterministic market snapshot persistence for connector ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from odds_aggregator.application.ingestion import MarketObservation

from .models import MarketSnapshotRecord

_SNAPSHOT_NAMESPACE = UUID("59cd1555-c07c-472d-9429-0f82773ad88d")


def persist_market_snapshot(
    session: Session,
    *,
    bookmaker_id: UUID,
    market_id: UUID,
    run_id: UUID,
    market: MarketObservation,
    is_live: bool,
    observed_at: datetime,
) -> UUID:
    source_updated_at = _source_timestamp(market)
    identity_timestamp = source_updated_at or observed_at
    selection_state = ";".join(
        sorted(
            "|".join(
                (
                    selection.source_id or selection.label,
                    _price_text(selection.decimal_odds),
                    "1" if selection.is_available else "0",
                )
            )
            for selection in market.selections
        )
    )
    identity = "|".join(
        (
            str(bookmaker_id),
            str(market_id),
            identity_timestamp.astimezone(UTC).isoformat(timespec="microseconds"),
            market.status.value,
            "1" if is_live else "0",
            selection_state,
        )
    )
    snapshot_id = uuid5(_SNAPSHOT_NAMESPACE, identity)
    session.execute(
        insert(MarketSnapshotRecord)
        .values(
            id=snapshot_id,
            bookmaker_id=bookmaker_id,
            market_id=market_id,
            run_id=run_id,
            observed_at=observed_at,
            source_updated_at=source_updated_at,
            is_live=is_live,
            market_status=market.status.value,
        )
        .on_conflict_do_nothing(index_elements=["id"])
    )
    return snapshot_id


def _source_timestamp(market: MarketObservation) -> datetime | None:
    timestamps = [
        selection.source_updated_at
        for selection in market.selections
        if selection.source_updated_at is not None
    ]
    if market.source_updated_at is not None:
        timestamps.append(market.source_updated_at)
    return max(timestamps) if timestamps else None


def _price_text(value: Decimal | None) -> str:
    return "" if value is None else format(value.normalize(), "f")
