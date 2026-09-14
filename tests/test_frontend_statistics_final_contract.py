from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.services.statistical_service import StatisticalService

client = TestClient(app, raise_server_exceptions=False)


def test_statistics_frontend_contract_rejects_non_integer_scope(monkeypatch):
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, role="analyst", is_active=True
    )
    called = False

    def fail_if_called(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run")

    monkeypatch.setattr(StatisticalService, "overview", fail_if_called)
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=1e3")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

    assert response.status_code == 422
    assert response.json()["detail"]
    assert called is False


def test_statistics_frontend_contract_rejects_scope_above_integer_bound():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, role="analyst", is_active=True
    )
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=2147483648")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

    assert response.status_code == 422
    assert response.json()["detail"]


def test_statistics_frontend_contract_rejects_unsupported_method():
    response = client.patch("/api/v1/statistics/overview")

    assert response.status_code == 405
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Method Not Allowed"}


def test_statistics_frontend_contract_preserves_request_id(monkeypatch):
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2, role="analyst", is_active=True
    )
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda **kwargs: {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        },
    )
    request_id = "frontend-statistics-final-252"
    try:
        response = client.get(
            "/api/v1/statistics/overview",
            headers={"X-Request-ID": request_id, "Accept": "application/json"},
        )
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 0,
    }
