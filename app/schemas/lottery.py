from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LotteryBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    country: str = Field(min_length=1, max_length=100)
    modality_code: str = Field(default="lotto", min_length=1, max_length=50)
    timezone: str = Field(default="America/Bogota", min_length=1, max_length=64)
    active: bool = True
    metadata_json: dict[str, Any] | None = None


class LotteryCreate(LotteryBase):
    pass


class LotteryUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    modality_code: str | None = Field(default=None, min_length=1, max_length=50)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    active: bool | None = None
    metadata_json: dict[str, Any] | None = None


class LotteryResponse(LotteryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
