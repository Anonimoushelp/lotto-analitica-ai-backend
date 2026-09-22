"""allow source records without provider draw number

Revision ID: d4f7a9c2e6b1
Revises: c8e5f2a7d1b4
Create Date: 2026-09-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4f7a9c2e6b1"
down_revision: Union[str, Sequence[str], None] = "c8e5f2a7d1b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "lottery_draws",
        "draw_number",
        existing_type=sa.String(length=50),
        nullable=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    missing = bind.execute(
        sa.text("SELECT COUNT(*) FROM lottery_draws WHERE draw_number IS NULL")
    ).scalar_one()
    if missing:
        raise RuntimeError(
            "Cannot downgrade: lottery_draws contains records without draw_number"
        )
    op.alter_column(
        "lottery_draws",
        "draw_number",
        existing_type=sa.String(length=50),
        nullable=False,
    )
