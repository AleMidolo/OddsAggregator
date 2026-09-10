"""Add prematch matching decision and bounded candidate audit tables."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003_match_decisions"
down_revision = "0002_nullable_unavailable_odds"
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TZ = sa.DateTime(timezone=True)
SCORE = sa.Numeric(7, 5)


def upgrade() -> None:
    op.create_table(
        "match_decisions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("bookmaker_id", UUID, sa.ForeignKey("bookmakers.id"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("decision_key", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("canonical_id", UUID),
        sa.Column("reason_code", sa.String(128), nullable=False),
        sa.Column("best_score", SCORE),
        sa.Column("runner_up_score", SCORE),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.UniqueConstraint("decision_key", name="uq_match_decision_key"),
        sa.CheckConstraint(
            "entity_type IN ('competition','participant','event','market','selection')",
            name="ck_match_decision_entity_type",
        ),
        sa.CheckConstraint(
            "state IN ('matched','created','ambiguous','unresolved','rejected')",
            name="ck_match_decision_state",
        ),
    )
    op.create_index(
        "ix_match_decisions_source",
        "match_decisions",
        ["bookmaker_id", "entity_type", "source_id", "created_at"],
    )
    op.create_table(
        "match_candidates",
        sa.Column(
            "decision_id",
            UUID,
            sa.ForeignKey("match_decisions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("candidate_id", UUID, primary_key=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", SCORE),
        sa.Column("disposition", sa.String(32), nullable=False),
        sa.Column("reason_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.UniqueConstraint(
            "decision_id",
            "candidate_id",
            name="uq_match_candidate_identity",
        ),
        sa.UniqueConstraint("decision_id", "rank", name="uq_match_candidate_rank"),
        sa.CheckConstraint("rank BETWEEN 1 AND 5", name="ck_match_candidate_rank"),
        sa.CheckConstraint(
            "disposition IN ('eligible','hard_rejected')",
            name="ck_match_candidate_disposition",
        ),
    )


def downgrade() -> None:
    op.drop_table("match_candidates")
    op.drop_index("ix_match_decisions_source", table_name="match_decisions")
    op.drop_table("match_decisions")
