"""restrict quota codes to the supported catalog

Revision ID: d8f5a1c2b3e4
Revises: c1e8f4a7b290

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d8f5a1c2b3e4"
down_revision: Union[str, Sequence[str], None] = "c1e8f4a7b290"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SUPPORTED_QUOTA_CODES = (
    "memberships.max",
    "lotteries.max",
    "draws.max",
    "predictions.max",
    "ai_generations.monthly",
)


def _quota_code_check(name: str) -> str:
    values = ", ".join(f"'{code}'" for code in SUPPORTED_QUOTA_CODES)
    return f"quota_code IN ({values})"


def upgrade() -> None:
    op.create_check_constraint(
        "ck_plan_quotas_supported_code",
        "plan_quotas",
        _quota_code_check("ck_plan_quotas_supported_code"),
    )
    op.create_check_constraint(
        "ck_tenant_quota_usages_supported_code",
        "tenant_quota_usages",
        _quota_code_check("ck_tenant_quota_usages_supported_code"),
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_tenant_quota_usages_supported_code",
        "tenant_quota_usages",
        type_="check",
    )
    op.drop_constraint(
        "ck_plan_quotas_supported_code",
        "plan_quotas",
        type_="check",
    )
