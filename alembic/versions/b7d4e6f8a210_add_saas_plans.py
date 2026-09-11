"""add SaaS plans

Revision ID: b7d4e6f8a210
Revises: 9c7e4a1b2d30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7d4e6f8a210"
down_revision: Union[str, Sequence[str], None] = "9c7e4a1b2d30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Initial limits for the built-in free tier. Keeping the seed in the migration
# makes a fresh deployment deterministic instead of silently disabling quota enforcement.
FREE_PLAN_QUOTAS = (
    ("memberships.max", 3),
    ("lotteries.max", 3),
    ("draws.max", 100),
    ("predictions.max", 50),
    ("ai_generations.monthly", 10),
)


def upgrade() -> None:
    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_plans_id", "plans", ["id"], unique=False)
    op.create_index("ix_plans_code", "plans", ["code"], unique=False)

    op.create_table(
        "plan_quotas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("quota_code", sa.String(length=80), nullable=False),
        sa.Column("limit_value", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "quota_code", name="uq_plan_quotas_plan_code"),
    )
    op.create_index("ix_plan_quotas_id", "plan_quotas", ["id"], unique=False)
    op.create_index("ix_plan_quotas_plan_id", "plan_quotas", ["plan_id"], unique=False)

    op.execute(
        sa.text(
            """
            INSERT INTO plans (code, name, is_active, created_at, updated_at)
            VALUES ('free', 'Free', TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
    )

    free_plan_quotas = sa.table(
        "plan_quotas",
        sa.column("plan_id", sa.Integer()),
        sa.column("quota_code", sa.String(length=80)),
        sa.column("limit_value", sa.BigInteger()),
    )
    free_plan_id = op.get_bind().execute(
        sa.text("SELECT id FROM plans WHERE code = 'free'")
    ).scalar_one()
    op.bulk_insert(
        free_plan_quotas,
        [
            {
                "plan_id": free_plan_id,
                "quota_code": quota_code,
                "limit_value": limit_value,
            }
            for quota_code, limit_value in FREE_PLAN_QUOTAS
        ],
    )

    op.add_column("tenants", sa.Column("plan_id", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            """
            UPDATE tenants
            SET plan_id = (SELECT id FROM plans WHERE code = 'free')
            WHERE plan_id IS NULL
            """
        )
    )
    op.alter_column("tenants", "plan_id", nullable=False)
    op.create_foreign_key(
        "fk_tenants_plan_id_plans",
        "tenants",
        "plans",
        ["plan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index("ix_tenants_plan_id", "tenants", ["plan_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tenants_plan_id", table_name="tenants")
    op.drop_constraint("fk_tenants_plan_id_plans", "tenants", type_="foreignkey")
    op.drop_column("tenants", "plan_id")
    op.drop_index("ix_plan_quotas_plan_id", table_name="plan_quotas")
    op.drop_index("ix_plan_quotas_id", table_name="plan_quotas")
    op.drop_table("plan_quotas")
    op.drop_index("ix_plans_code", table_name="plans")
    op.drop_index("ix_plans_id", table_name="plans")
    op.drop_table("plans")
