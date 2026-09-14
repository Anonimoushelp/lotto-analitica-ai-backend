from datetime import date
from typing import Any, ClassVar, Protocol

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator


class LotteryDrawPayload(BaseModel):
    """Canonical, source-neutral representation of an imported draw."""

    _MAX_METADATA_DEPTH: ClassVar[int] = 5
    _MAX_METADATA_NODES: ClassVar[int] = 256
    _MAX_METADATA_STRING_LENGTH: ClassVar[int] = 512
    _MAX_METADATA_KEY_LENGTH: ClassVar[int] = 128

    model_config = ConfigDict(extra="forbid")

    draw_number: str = Field(min_length=1, max_length=50)
    draw_date: date
    main_numbers: list[StrictInt] = Field(min_length=1, max_length=20)
    bonus_numbers: list[StrictInt] | None = Field(default=None, max_length=10)
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
    def validate_numbers(cls, value: list[StrictInt] | None) -> list[StrictInt] | None:
        if value is None:
            return None
        if any(number <= 0 for number in value):
            raise ValueError("Numbers must be positive integers")
        if len(value) != len(set(value)):
            raise ValueError("Numbers must be unique")
        return value

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        cls._validate_metadata_node(value, depth=0)
        return value

    @classmethod
    def _validate_metadata_node(cls, value: Any, depth: int) -> int:
        if depth > cls._MAX_METADATA_DEPTH:
            raise ValueError("Metadata nesting is too deep")

        if isinstance(value, dict):
            nodes = 1
            for key, child in value.items():
                if not isinstance(key, str) or not key.strip():
                    raise ValueError("Metadata keys must be non-empty strings")
                if len(key) > cls._MAX_METADATA_KEY_LENGTH:
                    raise ValueError("Metadata keys are too long")
                if any(char.isprintable() is False for char in key):
                    raise ValueError("Metadata contains invalid characters")
                nodes += cls._validate_metadata_node(child, depth + 1)
                if nodes > cls._MAX_METADATA_NODES:
                    raise ValueError("Metadata contains too many nodes")
            return nodes

        if isinstance(value, (list, tuple)):
            nodes = 1
            for child in value:
                nodes += cls._validate_metadata_node(child, depth + 1)
                if nodes > cls._MAX_METADATA_NODES:
                    raise ValueError("Metadata contains too many nodes")
            return nodes

        if isinstance(value, str):
            if len(value) > cls._MAX_METADATA_STRING_LENGTH:
                raise ValueError("Metadata strings are too long")
            if any(char.isprintable() is False for char in value):
                raise ValueError("Metadata contains invalid characters")

        return 1


class LotterySourceAdapter(Protocol):
    """Contract implemented by each external lottery source adapter."""

    source_name: str

    def parse_draw(self, payload: Any) -> LotteryDrawPayload:
        """Validate and normalize one provider payload into the canonical model."""
        ...
