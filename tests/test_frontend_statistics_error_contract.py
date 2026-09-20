from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.services.statistical_service import StatisticalService

client = TestClient(app)


@pytest.fixture
def authorized_analyst():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        role="analyst",
        is_active=True,
    )
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def test_statistics_viewer_is_denied_with_json_403():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=3,
        role="viewer",
        is_active=True,
    )
    try:
        response = client.get("/api/v1/statistics/overview")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

    assert response.status_code == 403
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"detail": "Insufficient permissions"}
    assert response.headers["X-Request-ID"]


def test_statistics_invalid_scope_returns_json_422_without_service_call(
    authorized_analyst, monkeypatch
):
    called = False

    def fail_if_called(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run for invalid lottery_id")

    monkeypatch.setattr(StatisticalService, "overview", fail_if_called)
    response = client.get("/api/v1/statistics/overview?lottery_id=1.5")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert called is False
    assert response.headers["X-Request-ID"]


def test_statistics_internal_failure_is_sanitized_and_correlated(
    authorized_analyst, monkeypatch
):
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("database password=super-secret traceback=/private/path")
        ),
    )
    request_id = "frontend-statistics-error-250"
    error_client = TestClient(app, raise_server_exceptions=False)

    response = error_client.get(
        "/api/v1/statistics/overview",
        headers={"X-Request-ID": request_id, "Accept": "application/json"},
    )

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["X-Request-ID"] == request_id
    assert response.json() == {"detail": "Internal server error"}
    assert "super-secret" not in response.text
    assert "traceback" not in response.text.lower()
    assert "/private/path" not in response.text


def test_statistics_ready_response_includes_cors_for_frontend_origin(
    authorized_analyst, monkeypatch
):
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda **kwargs: {
            "module_status": "READY",
            "algorithms_count": 6,
            "draws_analyzed": 10,
        },
    )

    response = client.get(
        "/api/v1/statistics/overview",
        headers={"Origin": "http://localhost:3000", "Accept": "application/json"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert response.json() == {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 10,
    }
