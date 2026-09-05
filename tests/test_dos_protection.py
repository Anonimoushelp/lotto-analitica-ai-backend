import pytest
from pydantic import ValidationError

from app.schemas.ai_prediction import AiPredictionRequest


def test_ai_prediction_request_has_bounded_workload_parameters():
    with pytest.raises(ValidationError):
        AiPredictionRequest(lottery_id=1, prediction_count=11)

    with pytest.raises(ValidationError):
        AiPredictionRequest(lottery_id=1, temperature=1.1)

    with pytest.raises(ValidationError):
        AiPredictionRequest(lottery_id=1, min_confidence_threshold=49)


def test_ai_prediction_request_accepts_workload_boundaries():
    request = AiPredictionRequest(
        lottery_id=1,
        prediction_count=10,
        temperature=1.0,
        min_confidence_threshold=95,
    )

    assert request.prediction_count == 10
    assert request.temperature == 1.0
    assert request.min_confidence_threshold == 95
