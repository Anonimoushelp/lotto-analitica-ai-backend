import json
from datetime import date, datetime, time
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

MAX_NUMBER_VALUE = 9999
MAX_MAIN_NUMBERS = 20
MAX_BONUS_NUMBERS = 10
MAX_METADATA_BYTES = 16 * 1024
MAX_VALIDATION_BYTES = 8 * 1024


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


def _validate_json_size(
    value: dict[str, Any] | None,
    *,
    field_name: str,
    max_bytes: int,
) -> dict[str, Any] | None:
    if value is None:
        return None

    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(serialized.encode("utf-8")) > max_bytes:
        raise ValueError(f"{field_name} cannot exceed {max_bytes} bytes")

    return value


class LotteryDrawBase(BaseModel):
    lottery_id: int = Field(gt=0)
    draw_type: str = Field(default="DEFAULT", min_length=1, max_length=50)
    draw_number: str = Field(min_length=1, max_length=50)
    draw_date: date
    draw_time: time | None = None
    main_numbers: list[int] = Field(
        min_length=1,
        max_length=MAX_MAIN_NUMBERS,
    )
    bonus_numbers: list[int] | None = Field(
        default=None,
        max_length=MAX_BONUS_NUMBERS,
    )
    source: str | None = Field(default=None, max_length=255)
    source_url: AnyHttpUrl | None = None
    source_timestamp: datetime | None = None
    metadata_json: dict[str, Any] | None = None
    validation_json: dict[str, Any] | None = None

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
    _validate_metadata_json = field_validator("metadata_json")(
        lambda value: _validate_json_size(
            value,
            field_name="metadata_json",
            max_bytes=MAX_METADATA_BYTES,
        )
    )
    _validate_validation_json = field_validator("validation_json")(
        lambda value: _validate_json_size(
            value,
            field_name="validation_json",
            max_bytes=MAX_VALIDATION_BYTES,
        )
    )


class LotteryDrawCreate(LotteryDrawBase):
    pass


class LotteryDrawUpdate(BaseModel):
    lottery_id: int | None = Field(default=None, gt=0)
    draw_type: str | None = Field(default=None, min_length=1, max_length=50)
    draw_number: str | None = Field(default=None, min_length=1, max_length=50)
    draw_date: date | None = None
    draw_time: time | None = None
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
    source_url: AnyHttpUrl | None = None
    source_timestamp: datetime | None = None
    metadata_json: dict[str, Any] | None = None
    validation_json: dict[str, Any] | None = None

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
    _validate_metadata_json = field_validator("metadata_json")(
        lambda value: _validate_json_size(
            value,
            field_name="metadata_json",
            max_bytes=MAX_METADATA_BYTES,
        )
    )
    _validate_validation_json = field_validator("validation_json")(
        lambda value: _validate_json_size(
            value,
            field_name="validation_json",
            max_bytes=MAX_VALIDATION_BYTES,
        )
    )


class LotteryDrawResponse(LotteryDrawBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
