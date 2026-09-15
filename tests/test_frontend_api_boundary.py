from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.services.statistical_service import StatisticalService

client = TestClient(app)


def test_frontend_boundary_exposes_cors_for_configured_origin():
    origin = "http://localhost:3000"
    response = client.options(
        "/api/v1/statistics/overview",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert response.headers["access-control-allow-methods"] == "GET, POST, PUT, PATCH, DELETE"
    assert "access-control-allow-credentials" not in response.headers


def test_frontend_boundary_rejects_unconfigured_origin():
    response = client.options(
        "/api/v1/statistics/overview",
        headers={
            "Origin": "http://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_frontend_boundary_preserves_json_contract_for_ready_response(monkeypatch):
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        role="analyst",
        is_active=True,
    )
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda **kwargs: {
            "module_status": "READY",
            "algorithms_count": 6,
            "draws_analyzed": 12,
        },
    )
    try:
        response = client.get(
            "/api/v1/statistics/overview?lottery_id=7",
            headers={"Accept": "application/json"},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 12,
    }
    assert "access-control-allow-origin" not in response.headers


def test_frontend_boundary_returns_json_error_for_missing_authentication():
    response = client.get(
        "/api/v1/statistics/overview",
        headers={"Accept": "application/json"},
    )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Not authenticated"}
