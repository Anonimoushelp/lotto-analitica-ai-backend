from datetime import date

import pytest
from pydantic import ValidationError

from app.integrations.lottery_sources import LotteryDrawPayload


def test_canonical_lottery_draw_payload_accepts_valid_data():
    result = LotteryDrawPayload(
        draw_number="2026-001",
        draw_date=date(2026, 9, 13),
        main_numbers=[5, 12, 23, 31, 42],
        bonus_numbers=[7],
        source="provider-example",
        metadata={"provider_draw_id": "abc-123"},
    )

    assert result.draw_number == "2026-001"
    assert result.main_numbers == [5, 12, 23, 31, 42]
    assert result.bonus_numbers == [7]


def test_canonical_lottery_draw_payload_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        LotteryDrawPayload(
            draw_number="2026-001",
            draw_date=date(2026, 9, 13),
            main_numbers=[5, 12, 23],
            source="provider-example",
            unexpected="must-be-rejected",
        )


def test_canonical_lottery_draw_payload_rejects_empty_numbers():
    with pytest.raises(ValidationError):
        LotteryDrawPayload(
            draw_number="2026-001",
            draw_date=date(2026, 9, 13),
            main_numbers=[],
            source="provider-example",
        )


def test_canonical_lottery_draw_payload_enforces_source_length():
    with pytest.raises(ValidationError):
        LotteryDrawPayload(
            draw_number="2026-001",
            draw_date=date(2026, 9, 13),
            main_numbers=[5],
            source="x" * 256,
        )
