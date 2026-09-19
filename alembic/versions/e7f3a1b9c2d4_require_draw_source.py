"""require draw source provenance

Revision ID: e7f3a1b9c2d4
Revises: d4e9f2a7b6c5
Create Date: 2026-09-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e7f3a1b9c2d4"
down_revision: Union[str, Sequence[str], None] = "d4e9f2a7b6c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE lottery_draws SET source = 'legacy-import' "
            "WHERE source IS NULL"
        )
    )
    op.alter_column(
        "lottery_draws",
        "source",
        existing_type=sa.String(length=255),
        nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "lottery_draws",
        "source",
        existing_type=sa.String(length=255),
        nullable=True,
    )
