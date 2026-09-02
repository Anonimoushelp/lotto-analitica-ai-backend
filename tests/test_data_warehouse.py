from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


BASE_URL = "/api/v1/data-warehouse"


def test_data_warehouse_kpis():
    response = client.get(f"{BASE_URL}/kpis")
    assert response.status_code == 200
    payload = response.json()
    assert "total_draws" in payload
    assert "total_lotteries" in payload
    assert "date_from" in payload
    assert "date_to" in payload
    assert "latest_draw_date" in payload


def test_data_warehouse_marts():
    response = client.get(f"{BASE_URL}/marts")
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    if payload:
        assert {"id", "name", "description", "source", "row_count"}.issubset(
            payload[0]
        )


def test_data_warehouse_cubes():
    response = client.get(f"{BASE_URL}/cubes")
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert payload[0]["id"] == "CUBE-DRAWS"
    assert {"name", "dimensions", "measures"}.issubset(payload[0])


def test_data_warehouse_query():
    response = client.post(
        f"{BASE_URL}/query",
        json={"limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "executed_at" in payload
    assert isinstance(payload["rows"], list)
    for row in payload["rows"]:
        assert {"lottery_id", "draw_count", "number_frequency"}.issubset(row)
        assert isinstance(row["number_frequency"], dict)


def test_data_warehouse_query_accepts_frontend_filters():
    response = client.post(
        f"{BASE_URL}/query",
        json={
            "lottery_id": 1,
            "date_from": "2020-01-01",
            "date_to": "2099-12-31",
            "limit": 1,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload["rows"], list)
    assert len(payload["rows"]) <= 1


def test_data_warehouse_query_rejects_invalid_limits():
    for limit in (0, 1001):
        response = client.post(
            f"{BASE_URL}/query",
            json={"limit": limit},
        )
        assert response.status_code == 422
