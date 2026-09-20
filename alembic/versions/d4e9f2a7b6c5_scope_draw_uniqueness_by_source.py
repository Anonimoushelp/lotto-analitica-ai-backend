"""scope draw uniqueness by provider source

Revision ID: d4e9f2a7b6c5
Revises: c1d8e7f4a2b6
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e9f2a7b6c5"
down_revision: Union[str, Sequence[str], None] = "c1d8e7f4a2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        "uq_lottery_draw_source_number",
        "lottery_draws",
        ["lottery_id", "source", "draw_number"],
    )
    op.create_unique_constraint(
        "uq_lottery_draw_source_date",
        "lottery_draws",
        ["lottery_id", "source", "draw_date"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_lottery_draw_source_number",
        "lottery_draws",
        type_="unique",
    )
    op.drop_constraint(
        "uq_lottery_draw_source_date",
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
