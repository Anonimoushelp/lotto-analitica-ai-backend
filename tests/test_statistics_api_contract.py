from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_statistical_overview_requires_lottery_scope():
    response = client.get("/api/v1/statistics/overview")
    assert response.status_code == 422


def test_statistical_overview_rejects_non_positive_scope():
    response = client.get("/api/v1/statistics/overview?lottery_id=0")
    assert response.status_code == 422


def test_statistical_overview_rejects_non_integer_scope():
    response = client.get("/api/v1/statistics/overview?lottery_id=abc")
    assert response.status_code == 422
