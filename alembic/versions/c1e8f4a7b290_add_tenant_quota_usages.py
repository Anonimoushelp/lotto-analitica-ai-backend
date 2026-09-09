"""add tenant quota usage ledger

Revision ID: c1e8f4a7b290
Revises: b7d4e6f8a210

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1e8f4a7b290"
down_revision: Union[str, Sequence[str], None] = "b7d4e6f8a210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tenant_quota_usages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("quota_code", sa.String(length=80), nullable=False),
        sa.Column("period_key", sa.String(length=16), nullable=False),
        sa.Column("usage_value", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "usage_value >= 0",
            name="ck_tenant_quota_usages_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "quota_code",
            "period_key",
            name="uq_tenant_quota_usages_scope",
        ),
    )
    op.create_index(
        "ix_tenant_quota_usages_id",
        "tenant_quota_usages",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_tenant_quota_usages_tenant_id",
        "tenant_quota_usages",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_quota_usages_tenant_id", table_name="tenant_quota_usages")
    op.drop_index("ix_tenant_quota_usages_id", table_name="tenant_quota_usages")
    op.drop_table("tenant_quota_usages")
