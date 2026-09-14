from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class LotteryDrawPayload(BaseModel):
    """Canonical, source-neutral representation of an imported draw."""

    model_config = ConfigDict(extra="forbid")

    draw_number: str = Field(min_length=1, max_length=50)
    draw_date: date
    main_numbers: list[int] = Field(min_length=1, max_length=20)
    bonus_numbers: list[int] | None = Field(default=None, max_length=10)
    source: str = Field(min_length=1, max_length=255)
    metadata: dict[str, Any] | None = None

    @field_validator("draw_number", "source")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(char.isprintable() is False for char in normalized):
            raise ValueError("Invalid identifier")
        return normalized

    @field_validator("main_numbers", "bonus_numbers")
    @classmethod
    def validate_numbers(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(isinstance(number, bool) or number <= 0 for number in value):
            raise ValueError("Numbers must be positive integers")
        if len(value) != len(set(value)):
            raise ValueError("Numbers must be unique")
        return value


class LotterySourceAdapter(Protocol):
    """Contract implemented by each external lottery source adapter."""

    source_name: str

    def parse_draw(self, payload: Any) -> LotteryDrawPayload:
        """Validate and normalize one provider payload into the canonical model."""
        ...
