from datetime import date, datetime

from pydantic import BaseModel, Field


class WarehouseKPIResponse(BaseModel):
    total_draws: int
    total_lotteries: int
    date_from: date | None = None
    date_to: date | None = None
    latest_draw_date: date | None = None


class DataMartResponse(BaseModel):
    id: str
    name: str
    description: str
    source: str
    row_count: int


class OlapCubeResponse(BaseModel):
    id: str
    name: str
    dimensions: list[str]
    measures: list[str]


class OlapQueryRequest(BaseModel):
    lottery_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=100, ge=1, le=1000)


class OlapQueryRow(BaseModel):
    lottery_id: int
    draw_count: int
    number_frequency: dict[str, int]


class OlapQueryResponse(BaseModel):
    executed_at: datetime
    rows: list[OlapQueryRow]
