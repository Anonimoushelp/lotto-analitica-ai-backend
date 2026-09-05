from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies.auth import get_current_user
from app.core.config import settings
from app.main import app
from app.schemas.ai_prediction import AiPatternInsight, AiPredictionRequest
from app.services.gemini_validator import validate_predictions
from app.services.statistical_service import StatisticalService

client = TestClient(app)


@pytest.fixture(autouse=True)
def authenticated_read_context():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        is_active=True,
    )
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def test_statistical_overview_contract(monkeypatch):
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda db: {
            "module_status": "READY",
            "algorithms_count": 8,
            "draws_analyzed": 42,
        },
    )

    response = client.get("/api/v1/statistics/overview")

    assert response.status_code == 200
    assert response.json() == {
        "module_status": "READY",
        "algorithms_count": 8,
        "draws_analyzed": 42,
    }


def test_prediction_model_status_is_unavailable_without_key(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "")

    response = client.get("/api/v1/predictions/model-status")

    assert response.status_code == 200
    assert response.json() == {
        "model_name": "Lotto-Net Gemini AI Core",
        "version": "not-configured",
        "status": "UNAVAILABLE",
    }


def test_prediction_model_status_is_idle_when_key_is_configured(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "test-key")

    response = client.get("/api/v1/predictions/model-status")

    assert response.status_code == 200
    assert response.json() == {
        "model_name": "Lotto-Net Gemini AI Core",
        "version": "gemini-2.5-flash",
        "status": "IDLE",
    }

    monkeypatch.setattr(settings, "gemini_api_key", "")


def test_gemini_validator_rejects_out_of_range_numbers():
    valid = {
        "predictions": [
            {"numbers": [1, 20, 300, 700, 1000], "confidence_score": 80}
        ]
    }
    invalid_low = {
        "predictions": [
            {"numbers": [0, 20, 300, 700, 1000], "confidence_score": 80}
        ]
    }
    invalid_high = {
        "predictions": [
            {"numbers": [1, 20, 300, 700, 1001], "confidence_score": 80}
        ]
    }

    assert validate_predictions(valid, expected_count=1) is True
    assert validate_predictions(invalid_low, expected_count=1) is False
    assert validate_predictions(invalid_high, expected_count=1) is False


def test_ai_pattern_insight_accepts_ai_category():
    insight = AiPatternInsight(
        id="ins-gemini",
        pattern_name="Análisis de patrones con Gemini",
        category="IA",
        weight_percentage=100.0,
        status="Detectado",
        description="Structured AI insight",
    )

    assert insight.category == "IA"


def test_ai_prediction_request_rejects_out_of_bounds_parameters():
    for field, value in (
        ("lottery_id", 0),
        ("prediction_count", 11),
        ("temperature", 0.0),
        ("temperature", 1.1),
        ("min_confidence_threshold", 49),
        ("min_confidence_threshold", 96),
    ):
        with pytest.raises(ValidationError):
            AiPredictionRequest(**{"lottery_id": 1, field: value})
