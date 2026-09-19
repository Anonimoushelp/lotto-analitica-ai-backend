import pytest
from pydantic import ValidationError

from app.schemas.lottery_draw import (
    LotteryDrawCreate,
    LotteryDrawUpdate,
)


def valid_payload() -> dict:
    return {
        "lottery_id": 1,
        "draw_number": "123",
        "draw_date": "2026-09-01",
        "main_numbers": [1, 7, 14, 22, 35],
        "bonus_numbers": [9],
        "source": "test",
    }


def test_draw_schema_accepts_valid_numbers() -> None:
    payload = LotteryDrawCreate(**valid_payload())
    assert payload.main_numbers == [1, 7, 14, 22, 35]
    assert payload.bonus_numbers == [9]


@pytest.mark.parametrize("numbers", [[1, 1, 7], [0, 7, 14], [1, 7, 1001]])
def test_draw_schema_rejects_invalid_main_numbers(numbers: list[int]) -> None:
    payload = valid_payload()
    payload["main_numbers"] = numbers
    with pytest.raises(ValidationError):
        LotteryDrawCreate(**payload)


def test_draw_schema_rejects_duplicate_bonus_numbers() -> None:
    payload = valid_payload()
    payload["bonus_numbers"] = [3, 3]
    with pytest.raises(ValidationError):
        LotteryDrawCreate(**payload)


def test_draw_update_schema_applies_same_number_validation() -> None:
    with pytest.raises(ValidationError):
        LotteryDrawUpdate(main_numbers=[4, 4])
    with pytest.raises(ValidationError):
        LotteryDrawUpdate(bonus_numbers=[1001])


def test_draw_schema_rejects_excessive_number_lists() -> None:
    payload = valid_payload()
    payload["main_numbers"] = list(range(1, 22))
    with pytest.raises(ValidationError):
        LotteryDrawCreate(**payload)


def test_draw_schema_accepts_metadata_within_limit() -> None:
    payload = valid_payload()
    payload["metadata_json"] = {"source": "official", "version": 1}
    draw = LotteryDrawCreate(**payload)
    assert draw.metadata_json == payload["metadata_json"]


def test_draw_schema_rejects_oversized_metadata() -> None:
    payload = valid_payload()
    payload["metadata_json"] = {"payloads": ["x" * 100 for _ in range(255)]}
    with pytest.raises(ValidationError):
        LotteryDrawCreate(**payload)


def test_draw_update_schema_rejects_oversized_metadata() -> None:
    with pytest.raises(ValidationError):
        LotteryDrawUpdate(
            metadata_json={"payloads": ["x" * 100 for _ in range(255)]}
        )


def test_draw_schema_rejects_overlapping_bonus_numbers() -> None:
    payload = valid_payload()
    payload["bonus_numbers"] = [7]
    with pytest.raises(ValidationError, match="bonus_numbers cannot overlap"):
        LotteryDrawCreate(**payload)


@pytest.mark.parametrize("field", ["source", "draw_number"])
def test_draw_schema_rejects_control_characters(field: str) -> None:
    payload = valid_payload()
    payload[field] = "valid\nvalue"
    with pytest.raises(ValidationError):
        LotteryDrawCreate(**payload)


def test_draw_schema_rejects_non_finite_metadata() -> None:
    payload = valid_payload()
    payload["metadata_json"] = {"score": float("nan")}
    with pytest.raises(ValidationError, match="non-finite"):
        LotteryDrawCreate(**payload)


def test_draw_schema_rejects_deep_metadata() -> None:
    payload = valid_payload()
    value = {}
    cursor = value
    for _ in range(7):
        cursor["nested"] = {}
        cursor = cursor["nested"]
    payload["metadata_json"] = value
    with pytest.raises(ValidationError, match="too complex"):
        LotteryDrawCreate(**payload)
