from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be blank")
    return normalized


class LotteryBase(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=150)
    country: str = Field(min_length=1, max_length=100)
    active: bool = True

    _validate_code = field_validator("code")(
        lambda value: _normalize_text(value, "code")
    )
    _validate_name = field_validator("name")(
        lambda value: _normalize_text(value, "name")
    )
    _validate_country = field_validator("country")(
        lambda value: _normalize_text(value, "country")
    )


class LotteryCreate(LotteryBase):
    pass


class LotteryUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=50)
    name: str | None = Field(default=None, min_length=1, max_length=150)
    country: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None

    _validate_code = field_validator("code")(
        lambda value: _normalize_text(value, "code")
    )
    _validate_name = field_validator("name")(
        lambda value: _normalize_text(value, "name")
    )
    _validate_country = field_validator("country")(
        lambda value: _normalize_text(value, "country")
    )


class LotteryResponse(LotteryBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
