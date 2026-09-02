from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_data_warehouse_kpis():
    response = client.get("/api/v1/data-warehouse/kpis")
    assert response.status_code == 200
    payload = response.json()
    assert "total_draws" in payload
    assert "total_lotteries" in payload


def test_data_warehouse_marts():
    response = client.get("/api/v1/data-warehouse/marts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_data_warehouse_cubes():
    response = client.get("/api/v1/data-warehouse/cubes")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["id"] == "CUBE-DRAWS"


def test_data_warehouse_query():
    response = client.post(
        "/api/v1/data-warehouse/query",
        json={"limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "executed_at" in payload
    assert isinstance(payload["rows"], list)
