"""Add a per-user JWT session version for immediate revocation.

Revision ID: d1e6a8c4f9b2
Revises: b8c3d7e1a2f4
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d1e6a8c4f9b2"
down_revision: Union[str, Sequence[str], None] = "b8c3d7e1a2f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "session_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "session_version")
