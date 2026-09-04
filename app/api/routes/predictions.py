from fastapi import APIRouter

from app.schemas.prediction import ModelStatusResponse
from app.services.prediction_service import PredictionService

router = APIRouter(
    prefix="/api/v1/predictions",
    tags=["Predictions"],
)


@router.get("/model-status", response_model=ModelStatusResponse)
def get_model_status():
    return PredictionService.model_status()
