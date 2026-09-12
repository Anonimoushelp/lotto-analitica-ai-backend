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


def test_statistical_overview_rejects_integer_overflow_scope():
    previous = _set_user("admin")
    try:
        response = client.get(
            "/api/v1/statistics/overview?lottery_id=999999999999999999999999999999"
        )
    finally:
        _restore_user(previous)

    assert response.status_code == 422


def test_statistical_overview_rejects_injection_like_scope():
    previous = _set_user("admin")
    try:
        response = client.get(
            "/api/v1/statistics/overview?lottery_id=1%20OR%201=1"
        )
    finally:
        _restore_user(previous)

    assert response.status_code == 422


def test_statistical_overview_does_not_fallback_for_unknown_lottery(monkeypatch):
    calls = []

    def fake_overview(*, db, lottery_id):
        calls.append(lottery_id)
        return {"module_status": "STANDBY", "algorithms_count": 0, "draws_analyzed": 0}

    monkeypatch.setattr(StatisticalService, "overview", fake_overview)
    previous = _set_user("analyst")
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=2147483647")
    finally:
        _restore_user(previous)

    assert response.status_code == 200
    assert calls == [2147483647]
    assert response.json()["draws_analyzed"] == 0


def test_statistical_overview_rejects_noncanonical_scope_types():
    previous = _set_user("admin")
    try:
        responses = [
            client.get("/api/v1/statistics/overview?lottery_id=true"),
            client.get("/api/v1/statistics/overview?lottery_id=null"),
            client.get("/api/v1/statistics/overview?lottery_id=0x10"),
        ]
    finally:
        _restore_user(previous)

    assert [response.status_code for response in responses] == [422, 422, 422]
