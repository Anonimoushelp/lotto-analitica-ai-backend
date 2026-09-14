from datetime import date
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class LotteryDrawPayload(BaseModel):
    """Canonical, source-neutral representation of an imported draw."""

    model_config = ConfigDict(extra="forbid")

    draw_number: str = Field(min_length=1, max_length=50)
    draw_date: date
    main_numbers: list[int] = Field(min_length=1, max_length=20)
    bonus_numbers: list[int] | None = Field(default=None, max_length=10)
    source: str = Field(min_length=1, max_length=255)
    metadata: dict[str, Any] | None = None


class LotterySourceAdapter(Protocol):
    """Contract implemented by each external lottery source adapter."""

    source_name: str

    def parse_draw(self, payload: Any) -> LotteryDrawPayload:
        """Validate and normalize one provider payload into the canonical model."""
        ...
