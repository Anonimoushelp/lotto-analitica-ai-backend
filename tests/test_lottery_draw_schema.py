import pytest
from pydantic import ValidationError

from app.schemas.lottery_draw import (
    MAX_METADATA_BYTES,
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
    }


def test_draw_schema_accepts_valid_numbers() -> None:
    payload = LotteryDrawCreate(**valid_payload())

    assert payload.main_numbers == [1, 7, 14, 22, 35]
    assert payload.bonus_numbers == [9]


@pytest.mark.parametrize(
    "numbers",
    [
        [1, 1, 7],
        [0, 7, 14],
        [1, 7, 1001],
    ],
)
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
    payload["metadata_json"] = {"payload": "x" * MAX_METADATA_BYTES}

    with pytest.raises(ValidationError, match="metadata_json cannot exceed"):
        LotteryDrawCreate(**payload)


def test_draw_update_schema_rejects_oversized_metadata() -> None:
    with pytest.raises(ValidationError, match="metadata_json cannot exceed"):
        LotteryDrawUpdate(metadata_json={"payload": "x" * MAX_METADATA_BYTES})

    
def test_draw_schema_accepts_normalized_non_numeric_result_group():
    payload = valid_payload()
    payload["main_numbers"] = None
    payload["bonus_numbers"] = None
    payload["result_groups"] = [
        {
            "group_code": "symbol",
            "position": 1,
            "value": "X",
            "numeric_value": None,
        }
    ]

    draw = LotteryDrawCreate(**payload)

    assert draw.main_numbers is None
    assert draw.result_groups[0].value == "X"


def test_draw_schema_rejects_duplicate_group_positions():
    payload = valid_payload()
    payload["result_groups"] = [
        {"group_code": "main", "position": 1, "value": "10"},
        {"group_code": "main", "position": 1, "value": "11"},
    ]

    with pytest.raises(ValidationError):
        LotteryDrawCreate(**payload)


def test_draw_update_schema_rejects_duplicate_group_positions():
    with pytest.raises(ValidationError):
        LotteryDrawUpdate(
            result_groups=[
                {"group_code": "main", "position": 1, "value": "10"},
                {"group_code": "main", "position": 1, "value": "11"},
            ]
        )


def test_draw_schema_requires_result_representation():
    payload = valid_payload()
    payload["main_numbers"] = None
    payload["bonus_numbers"] = None
    payload["result_groups"] = []

    with pytest.raises(ValidationError, match="result representation"):
        LotteryDrawCreate(**payload)
