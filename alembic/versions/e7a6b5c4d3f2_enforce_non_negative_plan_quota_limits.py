"""enforce non-negative plan quota limits

Revision ID: e7a6b5c4d3f2
Revises: d8f5a1c2b3e4

"""
from typing import Sequence, Union

from alembic import op

revision: str = "e7a6b5c4d3f2"
down_revision: Union[str, Sequence[str], None] = "d8f5a1c2b3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_plan_quotas_limit_non_negative",
        "plan_quotas",
        "limit_value >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_plan_quotas_limit_non_negative",
        "plan_quotas",
        type_="check",
    )
