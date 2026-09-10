from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class BookmakerRecord(Base):
    __tablename__ = "bookmakers"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SportRecord(Base):
    __tablename__ = "sports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class CompetitionRecord(Base):
    __tablename__ = "competitions"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sport_id: Mapped[UUID] = mapped_column(ForeignKey("sports.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8))
    gender: Mapped[str | None] = mapped_column(String(32))
    season: Mapped[str | None] = mapped_column(String(64))


class ParticipantRecord(Base):
    __tablename__ = "participants"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sport_id: Mapped[UUID] = mapped_column(ForeignKey("sports.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(8))


class EventRecord(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_sport_start_time", "sport_id", "start_time"),
        Index("ix_events_competition_start_time", "competition_id", "start_time"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    sport_id: Mapped[UUID] = mapped_column(ForeignKey("sports.id"), nullable=False)
    competition_id: Mapped[UUID | None] = mapped_column(ForeignKey("competitions.id"))
    name: Mapped[str | None] = mapped_column(String(255))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EventParticipantRecord(Base):
    __tablename__ = "event_participants"
    __table_args__ = (
        UniqueConstraint("event_id", "participant_id", name="uq_event_participant"),
        UniqueConstraint("event_id", "role", name="uq_event_role"),
    )

    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), primary_key=True)
    participant_id: Mapped[UUID] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    role: Mapped[str | None] = mapped_column(String(32))
    position: Mapped[int | None] = mapped_column(Integer)


class MarketRecord(Base):
    __tablename__ = "markets"
    __table_args__ = (Index("ix_markets_event_id", "event_id"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("events.id"), nullable=False)
    market_type: Mapped[str] = mapped_column(String(64), nullable=False)
    period: Mapped[str] = mapped_column(String(64), nullable=False)
    line: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    scope: Mapped[str | None] = mapped_column(String(64))
    variant: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SelectionRecord(Base):
    __tablename__ = "selections"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    selection_type: Mapped[str] = mapped_column(String(64), nullable=False)
    participant_id: Mapped[UUID | None] = mapped_column(ForeignKey("participants.id"))
    line: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    name: Mapped[str | None] = mapped_column(String(255))


class ConnectorRunRecord(Base):
    __tablename__ = "connector_runs"
    __table_args__ = (Index("ix_connector_runs_bookmaker_started", "bookmaker_id", "started_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    bookmaker_id: Mapped[UUID] = mapped_column(ForeignKey("bookmakers.id"), nullable=False)
    operation: Mapped[str] = mapped_column(String(128), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(255))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(128))
    error_summary: Mapped[str | None] = mapped_column(Text)


class MarketSnapshotRecord(Base):
    __tablename__ = "market_snapshots"
    __table_args__ = (
        Index(
            "ix_snapshots_market_bookmaker_observed",
            "market_id",
            "bookmaker_id",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    bookmaker_id: Mapped[UUID] = mapped_column(ForeignKey("bookmakers.id"), nullable=False)
    market_id: Mapped[UUID] = mapped_column(ForeignKey("markets.id"), nullable=False)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("connector_runs.id"), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_live: Mapped[bool] = mapped_column(Boolean, nullable=False)
    market_status: Mapped[str] = mapped_column(String(32), nullable=False)


class OddsQuoteRecord(Base):
    __tablename__ = "odds_quotes"
    __table_args__ = (
        UniqueConstraint("observation_key", name="uq_odds_quotes_observation_key"),
        Index(
            "ix_quotes_selection_bookmaker_observed",
            "selection_id",
            "bookmaker_id",
            "observed_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(ForeignKey("market_snapshots.id"), nullable=False)
    bookmaker_id: Mapped[UUID] = mapped_column(ForeignKey("bookmakers.id"), nullable=False)
    selection_id: Mapped[UUID] = mapped_column(ForeignKey("selections.id"), nullable=False)
    decimal_odds: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_key: Mapped[str] = mapped_column(String(64), nullable=False)


class SourceEntityMappingRecord(Base):
    __tablename__ = "source_entity_mappings"
    __table_args__ = (
        UniqueConstraint(
            "bookmaker_id",
            "entity_type",
            "source_id",
            name="uq_source_mapping_identity",
        ),
        Index("ix_source_mapping_lookup", "bookmaker_id", "entity_type", "source_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    bookmaker_id: Mapped[UUID] = mapped_column(ForeignKey("bookmakers.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_id: Mapped[UUID] = mapped_column(nullable=False)
    source_name: Mapped[str | None] = mapped_column(String(255))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    connector_version: Mapped[str | None] = mapped_column(String(128))


class ParticipantAliasRecord(Base):
    __tablename__ = "participant_aliases"
    __table_args__ = (
        UniqueConstraint("participant_id", "normalized_alias", name="uq_participant_alias"),
    )

    participant_id: Mapped[UUID] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    normalized_alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str | None] = mapped_column(String(128))


class CompetitionAliasRecord(Base):
    __tablename__ = "competition_aliases"
    __table_args__ = (
        UniqueConstraint("competition_id", "normalized_alias", name="uq_competition_alias"),
    )

    competition_id: Mapped[UUID] = mapped_column(ForeignKey("competitions.id"), primary_key=True)
    normalized_alias: Mapped[str] = mapped_column(String(255), primary_key=True)
    source: Mapped[str | None] = mapped_column(String(128))
