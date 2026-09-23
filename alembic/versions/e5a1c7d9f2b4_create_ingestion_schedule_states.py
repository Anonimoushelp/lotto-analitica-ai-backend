"""Create persistent ingestion scheduler state.

Revision ID: e5a1c7d9f2b4
Revises: d4f7a9c2e6b1
"""

from alembic import op
import sqlalchemy as sa

revision = "e5a1c7d9f2b4"
down_revision = "d4f7a9c2e6b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_schedule_states",
        sa.Column("job_key", sa.String(length=128), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_id", sa.String(length=36), nullable=True),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_attempts", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("job_key"),
    )


def downgrade() -> None:
    op.drop_table("ingestion_schedule_states")
