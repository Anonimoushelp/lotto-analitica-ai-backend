from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app

client = TestClient(app)


@pytest.fixture
def analyst_context():
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


def test_lottery_detail_rejects_non_positive_identifier(analyst_context):
    response = client.get("/api/v1/lotteries/0")
    assert response.status_code == 422
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.headers["X-Request-ID"]


def test_draw_detail_rejects_non_positive_identifier(analyst_context):
    response = client.get("/api/v1/draws/0")
    assert response.status_code == 422
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.headers["X-Request-ID"]


def test_draw_list_rejects_invalid_limit_without_service_call(monkeypatch, analyst_context):
    from app.services.lottery_draw_service import LotteryDrawService

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run for invalid pagination")

    monkeypatch.setattr(LotteryDrawService, "list_draws", fail_if_called)
    response = client.get("/api/v1/draws?limit=501")

    assert response.status_code == 422
    assert called is False


def test_draw_list_rejects_invalid_lottery_scope_without_service_call(
    monkeypatch, analyst_context
):
    from app.services.lottery_draw_service import LotteryDrawService

    called = False

    def fail_if_called(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run for invalid scope")

    monkeypatch.setattr(LotteryDrawService, "list_draws", fail_if_called)
    response = client.get("/api/v1/draws?lottery_id=0")

    assert response.status_code == 422
    assert called is False


def test_wrong_method_on_lotteries_returns_json_error():
    response = client.patch("/api/v1/lotteries")
    assert response.status_code == 405
    assert response.headers["Content-Type"].startswith("application/json")
    assert response.json()["detail"] == "Method Not Allowed"
    assert response.headers["X-Request-ID"]


def test_internal_path_details_are_not_exposed_on_not_found():
    response = client.get("/api/v1/lotteries/2147483647")
    assert response.status_code in {404, 422}
    assert "traceback" not in response.text.lower()
    assert "sqlalchemy" not in response.text.lower()
    assert "password" not in response.text.lower()
