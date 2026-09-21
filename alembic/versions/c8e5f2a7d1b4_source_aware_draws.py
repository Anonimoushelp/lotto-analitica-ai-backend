"""make lottery draws source-aware and multi-modality

Revision ID: c8e5f2a7d1b4
Revises: b7c4d9e2f1a3
Create Date: 2026-09-21

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8e5f2a7d1b4"
down_revision: Union[str, Sequence[str], None] = "b7c4d9e2f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lottery_draws",
        sa.Column(
            "draw_type",
            sa.String(length=50),
            nullable=False,
            server_default="DEFAULT",
        ),
    )
    op.add_column(
        "lottery_draws",
        sa.Column("draw_time", sa.Time(), nullable=True),
    )
    op.add_column(
        "lottery_draws",
        sa.Column("source_url", sa.String(length=2048), nullable=True),
    )
    op.add_column(
        "lottery_draws",
        sa.Column(
            "source_timestamp",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "lottery_draws",
        sa.Column("validation_json", sa.JSON(), nullable=True),
    )

    op.drop_constraint(
        "uq_lottery_draw_number",
        "lottery_draws",
        type_="unique",
    )
    op.drop_constraint(
        "uq_lottery_draw_date",
        "lottery_draws",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_lottery_draw_type_number",
        "lottery_draws",
        ["lottery_id", "draw_type", "draw_number"],
    )
    op.create_unique_constraint(
        "uq_lottery_draw_type_date",
        "lottery_draws",
        ["lottery_id", "draw_type", "draw_date"],
    )
    op.create_index(
        "ix_lottery_draws_lottery_type_date",
        "lottery_draws",
        ["lottery_id", "draw_type", "draw_date"],
    )

    op.alter_column(
        "lottery_draws",
        "draw_type",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_lottery_draws_lottery_type_date",
        table_name="lottery_draws",
    )
    op.drop_constraint(
        "uq_lottery_draw_type_date",
        "lottery_draws",
        type_="unique",
    )
    op.drop_constraint(
        "uq_lottery_draw_type_number",
        "lottery_draws",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_lottery_draw_number",
        "lottery_draws",
        ["lottery_id", "draw_number"],
    )
    op.create_unique_constraint(
        "uq_lottery_draw_date",
        "lottery_draws",
        ["lottery_id", "draw_date"],
    )

    op.drop_column("lottery_draws", "validation_json")
    op.drop_column("lottery_draws", "source_timestamp")
    op.drop_column("lottery_draws", "source_url")
    op.drop_column("lottery_draws", "draw_time")
    op.drop_column("lottery_draws", "draw_type")
