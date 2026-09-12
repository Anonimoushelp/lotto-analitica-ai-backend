from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture
def admin_context():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        is_active=True,
    )
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous


def test_statistics_requires_authentication():
    response = client.get("/api/v1/statistics/overview")
    assert response.status_code == 401
    assert response.headers["X-Request-ID"]


def test_statistics_rejects_malformed_scope_without_service_call(monkeypatch):
    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run for invalid query input")

    from app.services.statistical_service import StatisticalService

    monkeypatch.setattr(StatisticalService, "overview", fail_if_called)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        is_active=True,
    )
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=0")
        assert response.status_code == 422
        assert called is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_statistics_rejects_non_integer_scope():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        is_active=True,
    )
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=not-an-int")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_statistics_rejects_integer_overflow_scope():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role="admin",
        is_active=True,
    )
    try:
        response = client.get(
            "/api/v1/statistics/overview?lottery_id=999999999999999999999999999"
        )
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_unknown_route_is_json_and_non_sensitive():
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json() == {"detail": "Not Found"}
    assert "traceback" not in response.text.lower()
    assert "exception" not in response.text.lower()
    assert response.headers["X-Request-ID"]


def test_unsupported_method_is_json_and_non_sensitive():
    response = client.patch("/api/v1/statistics/overview")
    assert response.status_code == 405
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json()["detail"] == "Method Not Allowed"
    assert response.headers["X-Request-ID"]


def test_invalid_json_on_mutation_is_422_and_does_not_leak_details(admin_context):
    response = client.post(
        "/api/v1/lotteries",
        content="{invalid-json",
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "traceback" not in response.text.lower()
    assert "sqlalchemy" not in response.text.lower()
    assert response.headers["X-Request-ID"]


def test_empty_json_object_fails_schema_validation(admin_context):
    response = client.post(
        "/api/v1/lotteries",
        json={},
    )
    assert response.status_code == 422
    assert response.headers["X-Request-ID"]


def test_body_limit_rejects_large_payload_before_route_processing():
    payload = "x" * 1_048_577
    response = client.post(
        "/health",
        content=payload,
        headers={"Content-Type": "text/plain"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large"}
    assert response.headers["X-Request-ID"]
