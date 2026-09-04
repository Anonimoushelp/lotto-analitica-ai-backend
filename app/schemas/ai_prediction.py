from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    version: str
    status: Literal["INITIALIZED", "TRAINING", "IDLE", "UNAVAILABLE"]


class AiPredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lottery_id: int = Field(gt=0)
    strategy: Literal["conservador", "balanceado", "agresivo", "patrones"] = "balanceado"
    prediction_count: int = Field(default=3, ge=1, le=10)
    temperature: float = Field(default=0.7, ge=0.1, le=1.0)
    min_confidence_threshold: float = Field(default=80, ge=50, le=95)
    include_extra_number: bool = False


class AiPredictionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    numbers: list[int]
    extra_number: int | None = None
    confidence_score: float
    risk_level: Literal["Bajo", "Moderado", "Alto"]
    pattern_detected: str
    rationale: str
    expected_sum: int
    parity_ratio: str
    timestamp: str


class AiPatternInsight(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    pattern_name: str
    category: Literal["Frecuencia", "Mora", "Dispersión", "Anomalía", "IA"]
    weight_percentage: float
    status: Literal["Detectado", "En Observación", "Inactivo"]
    description: str


class AiEngineSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lottery_id: str
    lottery_name: str
    active_model: str
    model_version: str
    overall_confidence: float
    top_recommended_numbers: list[int]
    cold_recovery_candidates: list[int]
    recommended_strategy: str
    last_updated: str


class AiPredictionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: AiEngineSummary
    predictions: list[AiPredictionItem]
    insights: list[AiPatternInsight]
    model_status: ModelStatusResponse
