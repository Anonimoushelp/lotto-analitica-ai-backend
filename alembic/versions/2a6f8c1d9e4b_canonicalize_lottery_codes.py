"""Canonicalize lottery codes and enforce case-insensitive uniqueness.

Revision ID: 2a6f8c1d9e4b
Revises: f1a2b3c4d5e6
"""

from alembic import op

revision = "2a6f8c1d9e4b"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve the row already referenced by draws and remove only uppercase
    # catalog duplicates that have no persisted draws.
    op.execute(
        """
        DELETE FROM lotteries duplicate
        WHERE duplicate.id IN (
            SELECT candidate.id
            FROM lotteries candidate
            JOIN lotteries canonical
              ON lower(canonical.code) = lower(candidate.code)
             AND canonical.id < candidate.id
            WHERE candidate.code <> lower(candidate.code)
              AND NOT EXISTS (
                  SELECT 1 FROM lottery_draws d
                  WHERE d.lottery_id = candidate.id
              )
        )
        """
    )

    op.execute("UPDATE lotteries SET code = lower(trim(code))")

    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_lotteries_code_lower "
        "ON lotteries (lower(code))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lotteries_code_lower")
