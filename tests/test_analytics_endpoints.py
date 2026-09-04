from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.services.gemini_validator import validate_predictions
from app.services.statistical_service import StatisticalService

client = TestClient(app)


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
