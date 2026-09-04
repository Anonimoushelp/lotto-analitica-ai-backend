from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
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
        "version": "2.5-pro-ready",
        "status": "IDLE",
    }

    monkeypatch.setattr(settings, "gemini_api_key", "")
