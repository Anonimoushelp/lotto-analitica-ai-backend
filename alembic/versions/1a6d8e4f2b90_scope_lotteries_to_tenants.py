"""scope lotteries to tenants

Revision ID: 1a6d8e4f2b90
Revises: f4a8c2d91e7b

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1a6d8e4f2b90"
down_revision: Union[str, Sequence[str], None] = "f4a8c2d91e7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lotteries", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_lotteries_tenant_id_tenants",
        "lotteries",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.execute(
        sa.text(
            """
            UPDATE lotteries
            SET tenant_id = (
                SELECT id FROM tenants WHERE slug = 'default'
            )
            WHERE tenant_id IS NULL
            """
        )
    )

    op.alter_column("lotteries", "tenant_id", nullable=False)

    op.drop_index("ix_lotteries_code", table_name="lotteries")
    op.create_index("ix_lotteries_code", "lotteries", ["code"], unique=False)
    op.create_index("ix_lotteries_tenant_id", "lotteries", ["tenant_id"], unique=False)
    op.create_unique_constraint(
        "uq_lotteries_tenant_code",
        "lotteries",
        ["tenant_id", "code"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_lotteries_tenant_code", "lotteries", type_="unique")
    op.drop_index("ix_lotteries_tenant_id", table_name="lotteries")
    op.drop_index("ix_lotteries_code", table_name="lotteries")
    op.create_index("ix_lotteries_code", "lotteries", ["code"], unique=True)
    op.drop_constraint("fk_lotteries_tenant_id_tenants", "lotteries", type_="foreignkey")
    op.drop_column("lotteries", "tenant_id")
