from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LotteryBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    country: str = Field(min_length=1, max_length=100)
    active: bool = True


class LotteryCreate(LotteryBase):
    pass


class LotteryUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None


class LotteryResponse(LotteryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
