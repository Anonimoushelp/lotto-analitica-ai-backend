from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.core.rate_limit import ai_rate_limiter
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.prediction_service import PredictionService

client = TestClient(app)


def test_predictions_requires_authentication():
    response = client.post(
        "/api/v1/predictions",
        json={
            "lottery_id": 1,
            "strategy": "balanceado",
            "prediction_count": 1,
            "temperature": 0.2,
            "min_confidence_threshold": 60,
            "include_extra_number": False,
        },
    )

    assert response.status_code == 401


def test_predictions_rejects_unauthorized_role():
    viewer = User(id=10, email="viewer@example.com", password_hash="unused", role="viewer")

    def override_current_user():
        return viewer

    app.dependency_overrides[get_current_user] = override_current_user
    try:
        response = client.post(
            "/api/v1/predictions",
            json={
                "lottery_id": 1,
                "strategy": "balanceado",
                "prediction_count": 1,
                "temperature": 0.2,
                "min_confidence_threshold": 60,
                "include_extra_number": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


def test_predictions_allows_authorized_analyst_without_external_ai_call(monkeypatch):
    analyst = User(id=11, email="analyst@example.com", password_hash="unused", role="analyst")

    def override_current_user():
        return analyst

    def override_db():
        yield None

    def fake_generate(db, payload):
        return {
            "summary": {
                "lottery_id": str(payload.lottery_id),
                "lottery_name": "Test Lottery",
                "active_model": "test-model",
                "model_version": "test",
                "overall_confidence": 80.0,
                "top_recommended_numbers": [1, 2, 3, 4, 5],
                "cold_recovery_candidates": [6, 7, 8, 9],
                "recommended_strategy": payload.strategy,
                "last_updated": "2026-09-04T00:00:00+00:00",
            },
            "predictions": [
                {
                    "id": "test-pred-1",
                    "numbers": [1, 2, 3, 4, 5],
                    "extra_number": None,
                    "confidence_score": 80.0,
                    "risk_level": "Moderado",
                    "pattern_detected": "Test",
                    "rationale": "Test response",
                    "expected_sum": 15,
                    "parity_ratio": "2 Par / 3 Impar",
                    "timestamp": "2026-09-04T00:00:00+00:00",
                }
            ],
            "insights": [
                {
                    "id": "test-insight",
                    "pattern_name": "Test",
                    "category": "Frecuencia",
                    "weight_percentage": 100.0,
                    "status": "Detectado",
                    "description": "Test insight",
                }
            ],
            "model_status": {
                "model_name": "test-model",
                "version": "test",
                "status": "IDLE",
            },
        }

    monkeypatch.setattr(PredictionService, "generate", staticmethod(fake_generate))
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_db] = override_db
    try:
        response = client.post(
            "/api/v1/predictions",
            json={
                "lottery_id": 1,
                "strategy": "balanceado",
                "prediction_count": 1,
                "temperature": 0.2,
                "min_confidence_threshold": 60,
                "include_extra_number": False,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"]["lottery_id"] == "1"


def test_ai_rate_limiter_enforces_ten_requests_per_minute(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.count = 0

        def eval(self, *args):
            self.count += 1
            return self.count

    fake = FakeRedis()
    monkeypatch.setattr(ai_rate_limiter, "_redis", fake)

    results = [ai_rate_limiter.allow(123) for _ in range(11)]

    assert results[:10] == [True] * 10
    assert results[10] is False
