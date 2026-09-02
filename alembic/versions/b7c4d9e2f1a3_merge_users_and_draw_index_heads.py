"""merge users and draw index migration heads

Revision ID: b7c4d9e2f1a3
Revises: 9f2a7c1d4e6b, 8a7c2e1f4b6d
Create Date: 2026-09-02

"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b7c4d9e2f1a3"
down_revision: Union[str, Sequence[str], None] = ("9f2a7c1d4e6b", "8a7c2e1f4b6d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge the independent migration branches."""
    pass


def downgrade() -> None:
    """Restore the two parent heads when downgrading the merge revision."""
    pass
