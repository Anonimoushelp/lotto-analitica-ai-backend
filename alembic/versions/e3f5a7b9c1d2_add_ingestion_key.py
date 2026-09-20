"""Persist deterministic keys for source ingestion."""

from alembic import op
import sqlalchemy as sa

revision = "e3f5a7b9c1d2"
down_revision = "d1e4f7a9c2b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "lottery_draws",
        sa.Column("ingestion_key", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_lottery_draws_ingestion_key",
        "lottery_draws",
        ["ingestion_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lottery_draws_ingestion_key",
        table_name="lottery_draws",
    )
    op.drop_column("lottery_draws", "ingestion_key")
