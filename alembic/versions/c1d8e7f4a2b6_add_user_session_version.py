"""add user session version

Revision ID: c1d8e7f4a2b6
Revises: b7c4d9e2f1a3

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1d8e7f4a2b6"
down_revision: Union[str, Sequence[str], None] = "b7c4d9e2f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_version", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")
