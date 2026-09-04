from fastapi.testclient import TestClient

from app.main import app
from app.core.rate_limit import ai_rate_limiter

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
