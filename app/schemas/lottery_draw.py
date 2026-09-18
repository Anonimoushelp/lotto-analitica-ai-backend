import json
from datetime import date, datetime
from math import isfinite
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_NUMBER_VALUE = 1000
MAX_MAIN_NUMBERS = 20
MAX_BONUS_NUMBERS = 10
MAX_METADATA_BYTES = 16 * 1024
DEFAULT_DRAW_SOURCE = "legacy-import"


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


def _validate_metadata(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None

    def walk(node: Any, depth: int = 0, nodes: list[int] | None = None) -> None:
        if nodes is None:
            nodes = [0]
        nodes[0] += 1
        if depth > 5 or nodes[0] > 256:
            raise ValueError("metadata_json structure is too complex")
        if isinstance(node, dict):
            for key, child in node.items():
                if not isinstance(key, str) or not key.strip() or len(key) > 128:
                    raise ValueError("metadata_json contains an invalid key")
                if any(not char.isprintable() for char in key):
                    raise ValueError("metadata_json contains invalid characters")
                walk(child, depth + 1, nodes)
        elif isinstance(node, list):
            for child in node:
                walk(child, depth + 1, nodes)
        elif isinstance(node, str):
            if len(node) > 512 or any(not char.isprintable() for char in node):
                raise ValueError("metadata_json contains an invalid string")
        elif isinstance(node, float) and not isfinite(node):
            raise ValueError("metadata_json contains a non-finite number")
        elif node is not None and not isinstance(node, (bool, int, float)):
            raise ValueError("metadata_json contains an unsupported value")

    walk(value)
    serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(serialized.encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError(
            f"metadata_json cannot exceed {MAX_METADATA_BYTES} bytes"
        )

    return value


def _validate_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized or any(not char.isprintable() for char in normalized):
        raise ValueError(f"{field_name} must be a printable non-blank string")
    return normalized


def _validate_source(value: str) -> str:
    return _validate_identifier(value, "source")


def _validate_draw_number(value: str) -> str:
    return _validate_identifier(value, "draw_number")


def _validate_bonus_disjoint(main_numbers: list[int] | None, bonus_numbers: list[int] | None):
    if main_numbers is not None and bonus_numbers is not None and set(main_numbers) & set(bonus_numbers):
        raise ValueError("bonus_numbers cannot overlap main_numbers")


class LotteryDrawBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    source: str = Field(
        default=DEFAULT_DRAW_SOURCE,
        min_length=1,
        max_length=255,
    )
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
    _validate_draw_number = field_validator("draw_number")(_validate_draw_number)
    _validate_source = field_validator("source")(_validate_source)
    _validate_metadata_json = field_validator("metadata_json")(_validate_metadata)

    @model_validator(mode="after")
    def validate_bonus_disjointness(self):
        _validate_bonus_disjoint(self.main_numbers, self.bonus_numbers)
        return self


class LotteryDrawCreate(LotteryDrawBase):
    source: str = Field(
        min_length=1,
        max_length=255,
    )


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
    source: str | None = Field(default=None, min_length=1, max_length=255)
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
    _validate_draw_number = field_validator("draw_number")(_validate_draw_number)
    _validate_source = field_validator("source")(_validate_source)
    _validate_metadata_json = field_validator("metadata_json")(_validate_metadata)

    @model_validator(mode="after")
    def validate_bonus_disjointness(self):
        _validate_bonus_disjoint(self.main_numbers, self.bonus_numbers)
        return self


class LotteryDrawResponse(LotteryDrawBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
