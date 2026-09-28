"""Reconcile known incorrect Manizales draw identities.

The pre-verification parser persisted two historical rows with swapped draw
identities and placeholder result 2025. This migration corrects only those
exact rows using verified results:

- 4973 / 2026-09-16 / 0018 / series 300
- 4974 / 2026-09-23 / 1933 / series 219

The migration is intentionally idempotent. Its downgrade is a no-op because
reintroducing the known-invalid historical records would be unsafe.
"""

from alembic import op

revision = "b8c3d7e1a2f4"
down_revision = "2a6f8c1d9e4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE public.lottery_draws AS ld
        SET
            draw_number = '4973',
            main_numbers = '[18]'::jsonb,
            metadata_json = '{
                "raw_result": "0018",
                "digit_count": 4,
                "series": "300",
                "source_verified": true,
                "source_format": "reconciled_official_historical_result",
                "reconciled_from_verified_source": true
            }'::jsonb
        FROM public.lotteries AS l
        WHERE ld.lottery_id = l.id
          AND lower(l.code) = 'loteria_manizales'
          AND ld.draw_type = 'LOTERIA_MANIZALES_ORDINARY'
          AND ld.draw_number = '4974'
          AND ld.draw_date = DATE '2026-09-16'
          AND ld.main_numbers = '[2025]'::jsonb
        """
    )

    op.execute(
        """
        UPDATE public.lottery_draws AS ld
        SET
            draw_number = '4974',
            main_numbers = '[1933]'::jsonb,
            metadata_json = '{
                "raw_result": "1933",
                "digit_count": 4,
                "series": "219",
                "source_verified": true,
                "source_format": "reconciled_official_historical_result",
                "reconciled_from_verified_source": true
            }'::jsonb
        FROM public.lotteries AS l
        WHERE ld.lottery_id = l.id
          AND lower(l.code) = 'loteria_manizales'
          AND ld.draw_type = 'LOTERIA_MANIZALES_ORDINARY'
          AND ld.draw_number = '4975'
          AND ld.draw_date = DATE '2026-09-23'
          AND ld.main_numbers = '[2025]'::jsonb
        """
    )


def downgrade() -> None:
    # Do not reintroduce the previously verified-invalid draw identities.
    pass
