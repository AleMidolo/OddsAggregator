from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MatchDecisionRecord(Base):
    __tablename__ = "match_decisions"
    __table_args__ = (
        UniqueConstraint("decision_key", name="uq_match_decision_key"),
        Index(
            "ix_match_decisions_source",
            "bookmaker_id",
            "entity_type",
            "source_id",
            "created_at",
        ),
        CheckConstraint(
            "entity_type IN ('competition','participant','event','market','selection')",
            name="ck_match_decision_entity_type",
        ),
        CheckConstraint(
            "state IN ('matched','created','ambiguous','unresolved','rejected')",
            name="ck_match_decision_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    bookmaker_id: Mapped[UUID] = mapped_column(ForeignKey("bookmakers.id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(64), nullable=False)
    decision_key: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reason_code: Mapped[str] = mapped_column(String(128), nullable=False)
    best_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 5), nullable=True)
    runner_up_score: Mapped[Decimal | None] = mapped_column(Numeric(7, 5), nullable=True)
    evidence: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MatchCandidateRecord(Base):
    __tablename__ = "match_candidates"
    __table_args__ = (
        UniqueConstraint("decision_id", "candidate_id", name="uq_match_candidate_identity"),
        UniqueConstraint("decision_id", "rank", name="uq_match_candidate_rank"),
        CheckConstraint("rank BETWEEN 1 AND 5", name="ck_match_candidate_rank"),
        CheckConstraint(
            "disposition IN ('eligible','hard_rejected')",
            name="ck_match_candidate_disposition",
        ),
    )

    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("match_decisions.id", ondelete="CASCADE"),
        primary_key=True,
    )
    candidate_id: Mapped[UUID] = mapped_column(primary_key=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(7, 5), nullable=True)
    disposition: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
