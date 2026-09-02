from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LotteryDrawBase(BaseModel):
    lottery_id: int = Field(gt=0)
    draw_number: str = Field(min_length=1, max_length=50)
    draw_date: date
    main_numbers: list[int] = Field(min_length=1)
    bonus_numbers: list[int] | None = None
    source: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] | None = None


class LotteryDrawCreate(LotteryDrawBase):
    pass


class LotteryDrawUpdate(BaseModel):
    lottery_id: int | None = Field(default=None, gt=0)
    draw_number: str | None = Field(default=None, min_length=1, max_length=50)
    draw_date: date | None = None
    main_numbers: list[int] | None = Field(default=None, min_length=1)
    bonus_numbers: list[int] | None = None
    source: str | None = Field(default=None, max_length=255)
    metadata_json: dict[str, Any] | None = None


class LotteryDrawResponse(LotteryDrawBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
