from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.services.lottery_draw_service import LotteryDrawService

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


def test_draw_list_forwards_source_scope(monkeypatch):
    calls = []

    def fake_list_draws(*, db, lottery_id, source, limit):
        calls.append((lottery_id, source, limit))
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", fake_list_draws)
    previous = _set_user("analyst")
    try:
        response = client.get(
            "/api/v1/draws?lottery_id=10&source=baloto-colombia&limit=25"
        )
    finally:
        _restore_user(previous)

    assert response.status_code == 200
    assert response.json() == []
    assert calls == [(10, "baloto-colombia", 25)]


def test_draw_list_allows_source_only_scope(monkeypatch):
    calls = []

    def fake_list_draws(*, db, lottery_id, source, limit):
        calls.append((lottery_id, source, limit))
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", fake_list_draws)
    previous = _set_user("analyst")
    try:
        response = client.get("/api/v1/draws?source=miloto-colombia")
    finally:
        _restore_user(previous)

    assert response.status_code == 200
    assert calls == [(None, "miloto-colombia", 100)]


def test_draw_list_rejects_invalid_source_scope():
    previous = _set_user("analyst")
    try:
        responses = [
            client.get("/api/v1/draws?source="),
            client.get("/api/v1/draws?source=" + "a" * 256),
        ]
    finally:
        _restore_user(previous)

    assert [response.status_code for response in responses] == [422, 422]
