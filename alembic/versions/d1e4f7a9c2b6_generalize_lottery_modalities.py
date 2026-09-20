"""generalize lottery modalities and normalize draw results

Revision ID: d1e4f7a9c2b6
Revises: b7c4d9e2f1a3
Create Date: 2026-09-20

"""
from __future__ import annotations

import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d1e4f7a9c2b6"
down_revision: Union[str, Sequence[str], None] = "b7c4d9e2f1a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


def upgrade() -> None:
    op.add_column(
        "lotteries",
        sa.Column(
            "modality_code",
            sa.String(length=50),
            nullable=False,
            server_default="lotto",
        ),
    )
    op.add_column(
        "lotteries",
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="America/Bogota",
        ),
    )
    op.add_column(
        "lotteries",
        sa.Column(
            "metadata_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_lotteries_modality_code",
        "lotteries",
        ["modality_code"],
        unique=False,
    )

    op.create_table(
        "lottery_rules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lottery_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column(
            "config_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["lottery_id"],
            ["lotteries.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "lottery_id",
            "version",
            name="uq_lottery_rules_lottery_version",
        ),
    )
    op.create_index(
        "ix_lottery_rules_id",
        "lottery_rules",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_lottery_rules_lottery_id",
        "lottery_rules",
        ["lottery_id"],
        unique=False,
    )

    op.add_column(
        "lottery_draws",
        sa.Column("draw_datetime", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "lottery_draws",
        sa.Column("source_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "lottery_draws",
        sa.Column("source_reference", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "lottery_draws",
        sa.Column(
            "raw_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.alter_column("lottery_draws", "main_numbers", nullable=True)

    op.create_index(
        "ix_lottery_draws_draw_datetime",
        "lottery_draws",
        ["draw_datetime"],
        unique=False,
    )

    # A calendar date is no longer a natural key: a modality may have
    # multiple draws on the same date. Draw number remains the stable key.
    op.drop_constraint(
        "uq_lottery_draw_date",
        "lottery_draws",
        type_="unique",
    )

    op.create_table(
        "draw_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("draw_id", sa.Integer(), nullable=False),
        sa.Column("group_code", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value", sa.String(length=50), nullable=False),
        sa.Column("numeric_value", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["draw_id"],
            ["lottery_draws.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_draw_results_id",
        "draw_results",
        ["id"],
        unique=False,
    )
    op.create_index(
        "ix_draw_results_draw_id",
        "draw_results",
        ["draw_id"],
        unique=False,
    )
    op.create_index(
        "ix_draw_results_draw_group_position",
        "draw_results",
        ["draw_id", "group_code", "position"],
        unique=False,
    )

    # Backfill the normalized representation from the legacy fields.
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, main_numbers, bonus_numbers FROM lottery_draws"
        )
    ).fetchall()

    draw_results = sa.table(
        "draw_results",
        sa.column("draw_id", sa.Integer()),
        sa.column("group_code", sa.String()),
        sa.column("position", sa.Integer()),
        sa.column("value", sa.String()),
        sa.column("numeric_value", sa.Integer()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )

    from datetime import UTC, datetime

    values = []
    for row in rows:
        for group_code, raw_values in (
            ("main", _as_list(row.main_numbers)),
            ("bonus", _as_list(row.bonus_numbers)),
        ):
            for position, raw_value in enumerate(raw_values, start=1):
                try:
                    numeric_value = int(raw_value)
                except (TypeError, ValueError):
                    numeric_value = None
                values.append(
                    {
                        "draw_id": row.id,
                        "group_code": group_code,
                        "position": position,
                        "value": str(raw_value),
                        "numeric_value": numeric_value,
                        "created_at": datetime.now(UTC),
                    }
                )

    if values:
        op.bulk_insert(draw_results, values)

    op.create_unique_constraint(
        "uq_draw_results_draw_group_position",
        "draw_results",
        ["draw_id", "group_code", "position"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_draw_results_draw_group_position",
        "draw_results",
        type_="unique",
    )
    op.drop_index(
        "ix_draw_results_draw_group_position",
        table_name="draw_results",
    )
    op.drop_index("ix_draw_results_draw_id", table_name="draw_results")
    op.drop_index("ix_draw_results_id", table_name="draw_results")
    op.drop_table("draw_results")

    op.create_unique_constraint(
        "uq_lottery_draw_date",
        "lottery_draws",
        ["lottery_id", "draw_date"],
    )
    op.drop_index(
        "ix_lottery_draws_draw_datetime",
        table_name="lottery_draws",
    )
    op.drop_column("lottery_draws", "raw_payload")
    op.drop_column("lottery_draws", "source_reference")
    op.drop_column("lottery_draws", "source_type")
    op.drop_column("lottery_draws", "draw_datetime")
    op.alter_column("lottery_draws", "main_numbers", nullable=False)

    op.drop_index("ix_lottery_rules_lottery_id", table_name="lottery_rules")
    op.drop_index("ix_lottery_rules_id", table_name="lottery_rules")
    op.drop_table("lottery_rules")

    op.drop_index("ix_lotteries_modality_code", table_name="lotteries")
    op.drop_column("lotteries", "metadata_json")
    op.drop_column("lotteries", "timezone")
    op.drop_column("lotteries", "modality_code")
