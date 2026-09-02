from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_NUMBER_VALUE = 1000
MAX_MAIN_NUMBERS = 20
MAX_BONUS_NUMBERS = 10


def _validate_numbers(
    value: list[int] | None,
    *,
    field_name: str,
    max_items: int,
) -> list[int] | None:
    if value is None:
        return None

    if len(value) > max_items:
        raise ValueError(
            f"{field_name} cannot contain more than {max_items} numbers"
        )

    if any(number < 1 or number > MAX_NUMBER_VALUE for number in value):
        raise ValueError(
            f"{field_name} numbers must be between 1 and {MAX_NUMBER_VALUE}"
        )

    if len(value) != len(set(value)):
        raise ValueError(f"{field_name} cannot contain duplicate numbers")

    return value


class LotteryDrawBase(BaseModel):
    lottery_id: int = Field(gt=0)
    draw_number: str = Field(min_length=1, max_length=50)
    draw_date: date
    main_numbers: list[int] = Field(
        min_length=1,
        max_length=MAX_MAIN_NUMBERS,
    )
    bonus_numbers: list[int] | None = Field(
        default=None,
        max_length=MAX_BONUS_NUMBERS,
    )
    source: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] | None = None

    _validate_main_numbers = field_validator("main_numbers")(
        lambda value: _validate_numbers(
            value,
            field_name="main_numbers",
            max_items=MAX_MAIN_NUMBERS,
        )
    )
    _validate_bonus_numbers = field_validator("bonus_numbers")(
        lambda value: _validate_numbers(
            value,
            field_name="bonus_numbers",
            max_items=MAX_BONUS_NUMBERS,
        )
    )


class LotteryDrawCreate(LotteryDrawBase):
    pass


class LotteryDrawUpdate(BaseModel):
    lottery_id: int | None = Field(default=None, gt=0)
    draw_number: str | None = Field(default=None, min_length=1, max_length=50)
    draw_date: date | None = None
    main_numbers: list[int] | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_MAIN_NUMBERS,
    )
    bonus_numbers: list[int] | None = Field(
        default=None,
        max_length=MAX_BONUS_NUMBERS,
    )
    source: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] | None = None

    _validate_main_numbers = field_validator("main_numbers")(
        lambda value: _validate_numbers(
            value,
            field_name="main_numbers",
            max_items=MAX_MAIN_NUMBERS,
        )
    )
    _validate_bonus_numbers = field_validator("bonus_numbers")(
        lambda value: _validate_numbers(
            value,
            field_name="bonus_numbers",
            max_items=MAX_BONUS_NUMBERS,
        )
    )


class LotteryDrawResponse(LotteryDrawBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
