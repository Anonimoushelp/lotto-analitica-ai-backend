from __future__ import annotations

from app.services.gemini_validator import validate_predictions


def test_statistics_overview(client):
    response = client.get("/api/v1/statistics/overview")
    assert response.status_code == 200
    data = response.json()
    assert "algorithms_count" in data


def test_prediction_model_status(client):
    response = client.get("/api/v1/predictions/model-status")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Lotto-Net Gemini AI Core"
    assert "version" in data


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
