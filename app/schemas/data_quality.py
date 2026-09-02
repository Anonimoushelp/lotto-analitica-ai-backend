from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DataQualityRuleResult(BaseModel):
    rule_id: str
    name: str
    passed: int
    failed: int
    severity: Literal["INFO", "WARNING", "CRITICAL"]


class DataQualityDiscrepancy(BaseModel):
    id: str
    draw_id: int
    lottery_id: int
    draw_number: str
    draw_date: date
    rule_id: str
    description: str
    status: Literal["PENDING", "RESOLVED", "IGNORED"] = "PENDING"
    current_main_numbers: list[int]
    current_bonus_numbers: list[int] | None = None
    metadata: dict[str, Any] | None = None


class DataQualityAuditResponse(BaseModel):
    audit_id: str
    executed_at: datetime
    lottery_id: int | None
    total_draws: int
    clean_draws: int
    flagged_draws: int
    score: float
    rules: list[DataQualityRuleResult]
    discrepancies: list[DataQualityDiscrepancy]


class DataQualityReconcileRequest(BaseModel):
    strategy: Literal["PRESERVE_PRIMARY", "PRESERVE_CONFLICTING", "MANUAL_VALUE"]
    custom_main_numbers: list[int] | None = Field(default=None, min_length=1)
    custom_bonus_numbers: list[int] | None = None
    notes: str | None = None


class DataQualityReconcileResponse(BaseModel):
    discrepancy_id: str
    draw_id: int
    status: Literal["RESOLVED"]
    updated_database_record: bool
    draw: dict[str, Any]
    notes: str | None = None
