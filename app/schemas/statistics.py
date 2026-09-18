from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StatisticalOverviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_status: Literal["READY", "STANDBY"]
    algorithms_count: int = Field(ge=0)
    draws_analyzed: int = Field(ge=0)


class StatisticalNumberFrequency(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int
    frequency: int
