from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.ai_prediction import (
    AiPredictionRequest,
    AiPredictionResponse,
    ModelStatusResponse,
)
from app.services.prediction_service import PredictionService

router = APIRouter(
    prefix="/api/v1/predictions",
    tags=["Predictions"],
)


@router.get("/model-status", response_model=ModelStatusResponse)
def get_model_status():
    return PredictionService.model_status()


@router.post("", response_model=AiPredictionResponse)
def generate_predictions(
    payload: AiPredictionRequest,
    db: Session = Depends(get_db),
):
    return PredictionService.generate(db=db, payload=payload)
