from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.services.statistical_service import StatisticalService

client = TestClient(app, raise_server_exceptions=False)


def _set_user(role: str):
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role=role, is_active=True
    )
    return previous


def _restore_user(previous):
    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous


def test_statistical_overview_requires_authentication():
    previous = app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.get("/api/v1/statistics/overview")
    finally:
        if previous is not None:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 401


def test_statistical_overview_rejects_unauthorized_role():
    previous = _set_user("viewer")
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=1")
    finally:
        _restore_user(previous)
    assert response.status_code == 403
    assert response.json() == {"detail": "Insufficient permissions"}


def test_statistical_overview_allows_analyst_and_preserves_scope(monkeypatch):
    calls = []

    def fake_overview(*, db, lottery_id):
        calls.append(lottery_id)
        return {"module_status": "STANDBY", "algorithms_count": 0, "draws_analyzed": 0}

    monkeypatch.setattr(StatisticalService, "overview", fake_overview)
    previous = _set_user("analyst")
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=42")
    finally:
        _restore_user(previous)

    assert response.status_code == 200
    assert response.json() == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 0,
    }
    assert calls == [42]


def test_statistical_overview_does_not_silently_accept_malformed_scope():
    previous = _set_user("admin")
    try:
        responses = [
            client.get("/api/v1/statistics/overview?lottery_id=abc"),
            client.get("/api/v1/statistics/overview?lottery_id=1.5"),
            client.get("/api/v1/statistics/overview?lottery_id=-1"),
            client.get("/api/v1/statistics/overview?lottery_id=0"),
        ]
    finally:
        _restore_user(previous)

    assert [response.status_code for response in responses] == [422, 422, 422, 422]


def test_statistical_overview_does_not_expose_internal_errors(monkeypatch):
    def fail(*, db, lottery_id):
        raise RuntimeError("database secret should not leak")

    monkeypatch.setattr(StatisticalService, "overview", fail)
    previous = _set_user("admin")
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=1")
    finally:
        _restore_user(previous)

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "database secret should not leak" not in response.text
