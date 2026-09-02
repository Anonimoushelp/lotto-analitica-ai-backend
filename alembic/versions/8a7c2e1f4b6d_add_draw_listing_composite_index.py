"""add composite index for draw listing

Revision ID: 8a7c2e1f4b6d
Revises: 377b13f6e3b4
Create Date: 2026-09-02

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a7c2e1f4b6d"
down_revision: Union[str, Sequence[str], None] = "377b13f6e3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INDEX_NAME = "ix_lottery_draws_lottery_date_id"


def upgrade() -> None:
    """Create the composite index used by filtered draw listings."""
    op.create_index(
        INDEX_NAME,
        "lottery_draws",
        ["lottery_id", "draw_date", "id"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the composite draw listing index."""
    op.drop_index(INDEX_NAME, table_name="lottery_draws")
