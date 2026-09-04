from pydantic import BaseModel, ConfigDict


class StatisticalOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_status: str
    algorithms_count: int
    draws_analyzed: int


class StatisticalNumberFrequency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    frequency: int
