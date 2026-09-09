"""Initial normalized domain and historical odds schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None

UUID = sa.Uuid()
TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "bookmakers",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
    )
    op.create_table(
        "sports",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
    )
    op.create_table(
        "competitions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sport_id", UUID, sa.ForeignKey("sports.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(8)),
        sa.Column("gender", sa.String(32)),
        sa.Column("season", sa.String(64)),
    )
    op.create_table(
        "participants",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sport_id", UUID, sa.ForeignKey("sports.id"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("country_code", sa.String(8)),
    )
    op.create_table(
        "events",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("sport_id", UUID, sa.ForeignKey("sports.id"), nullable=False),
        sa.Column("competition_id", UUID, sa.ForeignKey("competitions.id")),
        sa.Column("name", sa.String(255)),
        sa.Column("start_time", TZ, nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_live", sa.Boolean(), nullable=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
    )
    op.create_index("ix_events_sport_start_time", "events", ["sport_id", "start_time"])
    op.create_index("ix_events_competition_start_time", "events", ["competition_id", "start_time"])
    op.create_table(
        "event_participants",
        sa.Column("event_id", UUID, sa.ForeignKey("events.id"), primary_key=True),
        sa.Column("participant_id", UUID, sa.ForeignKey("participants.id"), primary_key=True),
        sa.Column("role", sa.String(32)),
        sa.Column("position", sa.Integer()),
        sa.UniqueConstraint("event_id", "participant_id", name="uq_event_participant"),
        sa.UniqueConstraint("event_id", "role", name="uq_event_role"),
    )
    op.create_table(
        "markets",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("event_id", UUID, sa.ForeignKey("events.id"), nullable=False),
        sa.Column("market_type", sa.String(64), nullable=False),
        sa.Column("period", sa.String(64), nullable=False),
        sa.Column("line", sa.Numeric(18, 8)),
        sa.Column("scope", sa.String(64)),
        sa.Column("variant", sa.String(64)),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
    )
    op.create_index("ix_markets_event_id", "markets", ["event_id"])
    op.create_table(
        "selections",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("market_id", UUID, sa.ForeignKey("markets.id"), nullable=False),
        sa.Column("selection_type", sa.String(64), nullable=False),
        sa.Column("participant_id", UUID, sa.ForeignKey("participants.id")),
        sa.Column("line", sa.Numeric(18, 8)),
        sa.Column("name", sa.String(255)),
    )
    op.create_table(
        "connector_runs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("bookmaker_id", UUID, sa.ForeignKey("bookmakers.id"), nullable=False),
        sa.Column("operation", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(255)),
        sa.Column("started_at", TZ, nullable=False),
        sa.Column("finished_at", TZ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accepted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejected_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(128)),
        sa.Column("error_summary", sa.Text()),
    )
    op.create_index("ix_connector_runs_bookmaker_started", "connector_runs", ["bookmaker_id", "started_at"])
    op.create_table(
        "market_snapshots",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("bookmaker_id", UUID, sa.ForeignKey("bookmakers.id"), nullable=False),
        sa.Column("market_id", UUID, sa.ForeignKey("markets.id"), nullable=False),
        sa.Column("run_id", UUID, sa.ForeignKey("connector_runs.id"), nullable=False),
        sa.Column("observed_at", TZ, nullable=False),
        sa.Column("source_updated_at", TZ),
        sa.Column("is_live", sa.Boolean(), nullable=False),
        sa.Column("market_status", sa.String(32), nullable=False),
    )
    op.create_index(
        "ix_snapshots_market_bookmaker_observed",
        "market_snapshots",
        ["market_id", "bookmaker_id", "observed_at"],
    )
    op.create_table(
        "odds_quotes",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("snapshot_id", UUID, sa.ForeignKey("market_snapshots.id"), nullable=False),
        sa.Column("bookmaker_id", UUID, sa.ForeignKey("bookmakers.id"), nullable=False),
        sa.Column("selection_id", UUID, sa.ForeignKey("selections.id"), nullable=False),
        sa.Column("decimal_odds", sa.Numeric(18, 8), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("observed_at", TZ, nullable=False),
        sa.Column("source_updated_at", TZ),
        sa.Column("observation_key", sa.String(64), nullable=False),
        sa.UniqueConstraint("observation_key", name="uq_odds_quotes_observation_key"),
    )
    op.create_index(
        "ix_quotes_selection_bookmaker_observed",
        "odds_quotes",
        ["selection_id", "bookmaker_id", "observed_at"],
    )
    op.create_table(
        "source_entity_mappings",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("bookmaker_id", UUID, sa.ForeignKey("bookmakers.id"), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("canonical_id", UUID, nullable=False),
        sa.Column("source_name", sa.String(255)),
        sa.Column("first_seen_at", TZ, nullable=False),
        sa.Column("last_seen_at", TZ, nullable=False),
        sa.Column("connector_version", sa.String(128)),
        sa.UniqueConstraint(
            "bookmaker_id", "entity_type", "source_id", name="uq_source_mapping_identity"
        ),
    )
    op.create_index(
        "ix_source_mapping_lookup",
        "source_entity_mappings",
        ["bookmaker_id", "entity_type", "source_id"],
    )
    op.create_table(
        "participant_aliases",
        sa.Column("participant_id", UUID, sa.ForeignKey("participants.id"), primary_key=True),
        sa.Column("normalized_alias", sa.String(255), primary_key=True),
        sa.Column("source", sa.String(128)),
        sa.UniqueConstraint("participant_id", "normalized_alias", name="uq_participant_alias"),
    )
    op.create_table(
        "competition_aliases",
        sa.Column("competition_id", UUID, sa.ForeignKey("competitions.id"), primary_key=True),
        sa.Column("normalized_alias", sa.String(255), primary_key=True),
        sa.Column("source", sa.String(128)),
        sa.UniqueConstraint("competition_id", "normalized_alias", name="uq_competition_alias"),
    )


def downgrade() -> None:
    for table in [
        "competition_aliases",
        "participant_aliases",
        "source_entity_mappings",
        "odds_quotes",
        "market_snapshots",
        "connector_runs",
        "selections",
        "markets",
        "event_participants",
        "events",
        "participants",
        "competitions",
        "sports",
        "bookmakers",
    ]:
        op.drop_table(table)
