from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app
from app.schemas.statistics import StatisticalOverviewResponse
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


def test_statistics_overview_returns_standby_contract(authorized_analyst, monkeypatch):
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda **kwargs: {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        },
    )

    response = client.get("/api/v1/statistics/overview")

    assert response.status_code == 200
    assert response.json() == {
        "module_status": "STANDBY",
        "algorithms_count": 0,
        "draws_analyzed": 0,
    }
    StatisticalOverviewResponse.model_validate(response.json())


def test_statistics_overview_returns_ready_contract(authorized_analyst, monkeypatch):
    monkeypatch.setattr(
        StatisticalService,
        "overview",
        lambda **kwargs: {
            "module_status": "READY",
            "algorithms_count": 6,
            "draws_analyzed": 12,
        },
    )

    response = client.get("/api/v1/statistics/overview?lottery_id=7")

    assert response.status_code == 200
    assert response.json() == {
        "module_status": "READY",
        "algorithms_count": 6,
        "draws_analyzed": 12,
    }
    StatisticalOverviewResponse.model_validate(response.json())


def test_statistics_overview_preserves_lottery_filter(authorized_analyst, monkeypatch):
    captured = {}

    def fake_overview(**kwargs):
        captured.update(kwargs)
        return {
            "module_status": "STANDBY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }

    monkeypatch.setattr(StatisticalService, "overview", fake_overview)

    response = client.get("/api/v1/statistics/overview?lottery_id=42")

    assert response.status_code == 200
    assert captured["lottery_id"] == 42


def test_statistics_overview_rejects_invalid_query_before_service(
    authorized_analyst, monkeypatch
):
    called = False

    def fail_if_called(**kwargs):
        nonlocal called
        called = True
        raise AssertionError("service must not run for invalid lottery_id")

    monkeypatch.setattr(StatisticalService, "overview", fail_if_called)

    response = client.get("/api/v1/statistics/overview?lottery_id=0")

    assert response.status_code == 422
    assert called is False


def test_statistics_response_schema_forbids_extra_fields():
    with pytest.raises(ValueError):
        StatisticalOverviewResponse.model_validate(
            {
                "module_status": "READY",
                "algorithms_count": 6,
                "draws_analyzed": 12,
                "unexpected": True,
            }
        )
