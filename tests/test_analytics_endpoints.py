from fastapi.testclient import TestClient

from app.main import app
from app.services.gemini_validator import validate_predictions

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


def test_gemini_validator_rejects_out_of_range_numbers():
    valid = {"predictions": [{"numbers": [1, 20, 300, 700, 1000], "confidence_score": 85}]}
    invalid_low = {"predictions": [{"numbers": [0, 20, 300, 700, 1000], "confidence_score": 85}]}
    invalid_high = {"predictions": [{"numbers": [1, 20, 300, 700, 1001], "confidence_score": 85}]}
    assert validate_predictions(valid, 1)
    assert not validate_predictions(invalid_low, 1)
    assert not validate_predictions(invalid_high, 1)
