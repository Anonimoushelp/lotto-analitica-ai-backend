"""Security and contract tests for the AI prediction surface."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.services.prediction_service import PredictionService


def test_prediction_request_rejects_unknown_fields():
    from app.schemas.ai_prediction import AiPredictionRequest

    with pytest.raises(ValidationError):
        AiPredictionRequest(
            lottery_id=1,
            strategy="balanceado",
            prediction_count=1,
            temperature=0.7,
            min_confidence_threshold=50,
            include_extra_number=False,
            unexpected="rejected",
        )


@pytest.mark.asyncio
async def test_prediction_service_requires_selected_lottery():
    class FakeScalar:
        def scalar_one_or_none(self):
            return None

    class FakeSession:
        async def execute(self, *_args, **_kwargs):
            return FakeScalar()

    with pytest.raises(HTTPException) as exc:
        await PredictionService().generate(
            FakeSession(),
            SimpleNamespace(lottery_id=999999, prediction_count=1),
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Lottery not found"


def test_predictions_route_requires_authentication():
    client = TestClient(app)
    response = client.post(
        "/api/v1/predictions",
        json={
            "lottery_id": 1,
            "strategy": "balanceado",
            "prediction_count": 1,
            "temperature": 0.7,
            "min_confidence_threshold": 50,
            "include_extra_number": False,
        },
    )
    assert response.status_code in {401, 403}
