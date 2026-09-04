from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_statistics_overview():
    response = client.get("/api/v1/statistics/overview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["algorithmsCount"] == 8
    assert payload["status"] == "active"


def test_prediction_model_status():
    response = client.get("/api/v1/predictions/model-status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "Gemini"
    assert payload["version"] in {"gemini-2.5-flash", "not-configured"}
    assert payload["status"] in {"IDLE", "UNAVAILABLE"}
