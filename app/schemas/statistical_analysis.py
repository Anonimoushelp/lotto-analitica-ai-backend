from pydantic import BaseModel, ConfigDict


class StatisticalAnalysisResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    module_status: str
    lottery_id: int | None
    draws_analyzed: int
    algorithms_count: int
    number_frequency: dict[int, int]
    number_recency: dict[int, dict[str, int]]
    even_odd_distribution: dict[str, int]
    sum_distribution: dict
    pair_frequency: dict[str, int]
    consecutive_numbers: dict[str, int]
