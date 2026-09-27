from pydantic import BaseModel, ConfigDict


class StatisticalAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_status: str
    lottery_id: int
    draws_analyzed: int
    algorithms_count: int
    frequencies: list[dict]
    hot_numbers: list[int]
    cold_numbers: list[int]
    odd_even: dict
    ranges: list[dict]
    consecutive_patterns: list[dict]
    recency_order: list[int]
