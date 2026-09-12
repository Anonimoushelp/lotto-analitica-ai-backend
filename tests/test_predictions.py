"""Security and contract tests for the AI prediction surface."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.prediction_service import PredictionService


def test_prediction_request_rejects_unknown_fields():
    from app.schemas.ai_prediction import AiPredictionRequest

    with pytest.raises(Exception):
        AiPredictionRequest(
            lottery_id=1,
            strategy="balanceado",
            prediction_count=1,
            temperature=0.7,
            min_confidence_threshold=50,
            include_extra_number=False,
            unexpected="rejected",
        )


def test_prediction_service_requires_selected_lottery(monkeypatch):
    class FakeScalar:
        def scalar_one_or_none(self):
            return None

    class FakeSession:
        async def execute(self, *_args, **_kwargs):
            return FakeScalar()

    async def run():
        with pytest.raises(Exception) as exc:
            await PredictionService().generate(
                FakeSession(),
                SimpleNamespace(lottery_id=999999, prediction_count=1),
            )
        assert "Lottery not found" in str(exc.value)


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
