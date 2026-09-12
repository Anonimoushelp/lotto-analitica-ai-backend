"""Security and contract tests for the AI prediction surface."""

from types import SimpleNamespace

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.schemas.ai_prediction import AiPredictionRequest
from app.services.prediction_service import PredictionService


def test_prediction_request_rejects_unknown_fields():
    try:
        AiPredictionRequest(
            lottery_id=1,
            strategy="balanceado",
            prediction_count=1,
            temperature=0.7,
            min_confidence_threshold=50,
            include_extra_number=False,
            unexpected="rejected",
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Unknown request fields must be rejected")


def test_prediction_service_requires_selected_lottery():
    class FakeSession:
        def get(self, *_args, **_kwargs):
            return None

    try:
        PredictionService().generate(
            FakeSession(),
            SimpleNamespace(lottery_id=999999, prediction_count=1),
        )
    except HTTPException as exc:
        assert exc.status_code == 404
        assert exc.detail == "Lottery not found"
    else:
        raise AssertionError("Missing lottery must raise HTTPException")


def test_prediction_service_fails_closed_without_verified_rule_catalog():
    class FakeSession:
        def get(self, *_args, **_kwargs):
            return SimpleNamespace(id=1, code="UNVERIFIED", name="Unverified")

    try:
        PredictionService().generate(
            FakeSession(),
            SimpleNamespace(
                lottery_id=1,
                prediction_count=1,
                include_extra_number=False,
            ),
        )
    except HTTPException as exc:
        assert exc.status_code == 422
        assert exc.detail == "AI predictions require a verified lottery rule catalog"
    else:
        raise AssertionError("Unverified lottery rules must block AI generation")


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
