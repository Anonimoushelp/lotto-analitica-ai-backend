import redis
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin_or_analyst
from app.core.config import settings
from app.core.rate_limit import ai_rate_limiter
from app.db.session import get_db
from app.models.user import User
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
    user: User = Depends(require_admin_or_analyst),
):
    try:
        allowed = ai_rate_limiter.allow(user.id)
    except redis.RedisError:
        if settings.environment == "production":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI prediction service temporarily unavailable",
            ) from None
        allowed = True

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many AI prediction requests. Try again later.",
            headers={"Retry-After": "60"},
        )

    return PredictionService.generate(db=db, payload=payload)
