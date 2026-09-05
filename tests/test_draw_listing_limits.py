# ruff: noqa: I001

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.services.lottery_draw_service import LotteryDrawService


client = TestClient(app)


@pytest.fixture(autouse=True)
def authenticated_read_context():
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


def test_draw_list_uses_bounded_default_limit(monkeypatch):
    captured = {}

    def fake_list_draws(db, lottery_id=None, limit=100):
        captured["lottery_id"] = lottery_id
        captured["limit"] = limit
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", fake_list_draws)

    response = client.get("/api/v1/draws")

    assert response.status_code == 200
    assert captured["lottery_id"] is None
    assert captured["limit"] == 100


def test_draw_list_accepts_configured_limit(monkeypatch):
    captured = {}

    def fake_list_draws(db, lottery_id=None, limit=100):
        captured["limit"] = limit
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", fake_list_draws)

    response = client.get("/api/v1/draws?lottery_id=1&limit=250")

    assert response.status_code == 200
    assert captured["limit"] == 250


def test_draw_list_rejects_invalid_limit(monkeypatch):
    called = False

    def fake_list_draws(db, lottery_id=None, limit=100):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", fake_list_draws)

    assert client.get("/api/v1/draws?limit=0").status_code == 422
    assert client.get("/api/v1/draws?limit=501").status_code == 422
    assert not called
