"""Allow unavailable odds observations without fabricated prices."""

import sqlalchemy as sa
from alembic import op

revision = "0002_nullable_unavailable_odds"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "odds_quotes",
        "decimal_odds",
        existing_type=sa.Numeric(18, 8),
        nullable=True,
    )


def downgrade() -> None:
    # The previous schema cannot represent unavailable observations without a price.
    op.execute(sa.text("DELETE FROM odds_quotes WHERE decimal_odds IS NULL"))
    op.alter_column(
        "odds_quotes",
        "decimal_odds",
        existing_type=sa.Numeric(18, 8),
        nullable=False,
    )
