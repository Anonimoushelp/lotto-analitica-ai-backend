# ruff: noqa: I001

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.tenant import TenantContext, get_tenant_context
from app.main import app
from app.schemas.lottery_draw import LotteryDrawUpdate
from app.services.lottery_draw_service import LotteryDrawService


client = TestClient(app)


@pytest.fixture(autouse=True)
def authenticated_read_context():
    previous = app.dependency_overrides.get(get_tenant_context)
    app.dependency_overrides[get_tenant_context] = lambda: TenantContext(
        user_id=1,
        tenant_id=1,
        membership_id=1,
        role="admin",
    )
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_tenant_context, None)
        else:
            app.dependency_overrides[get_tenant_context] = previous


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


def test_draw_list_rejects_sql_injection_like_lottery_id(monkeypatch):
    called = False

    def fake_list_draws(db, lottery_id=None, limit=100):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(LotteryDrawService, "list_draws", fake_list_draws)

    response = client.get("/api/v1/draws?lottery_id=1%20OR%201%3D1")

    assert response.status_code == 422
    assert not called


def test_draw_update_schema_ignores_unrecognized_mass_assignment_fields():
    payload = LotteryDrawUpdate.model_validate(
        {
            "draw_number": "123",
            "password_hash": "attacker-controlled",
            "role": "admin",
        }
    )

    assert payload.model_dump(exclude_unset=True) == {"draw_number": "123"}
