from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.db.session import get_db
from app.main import app
from app.services.statistical_service import StatisticalService

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_overrides():
    previous_user = app.dependency_overrides.get(get_current_user)
    previous_db = app.dependency_overrides.get(get_db)
    yield
    if previous_user is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous_user
    if previous_db is None:
        app.dependency_overrides.pop(get_db, None)
    else:
        app.dependency_overrides[get_db] = previous_db


def set_user(role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
    )


def override_db():
    yield None


@pytest.mark.parametrize("role", ["viewer", "service"])
def test_statistics_rejects_non_analyst_roles(role, monkeypatch):
    set_user(role)
    app.dependency_overrides[get_db] = override_db
    called = False

    def fake_overview(db):
        nonlocal called
        called = True
        return {
            "module_status": "READY",
            "algorithms_count": 0,
            "draws_analyzed": 0,
        }

    monkeypatch.setattr(StatisticalService, "overview", fake_overview)

    response = client.get("/api/v1/statistics/overview")

    assert response.status_code == 403
    assert called is False


@pytest.mark.parametrize("role", ["viewer", "service"])
def test_prediction_model_status_rejects_non_analyst_roles(role):
    set_user(role)

    response = client.get("/api/v1/predictions/model-status")

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["viewer", "service"])
def test_prediction_generation_rejects_non_analyst_roles(role):
    set_user(role)

    response = client.post(
        "/api/v1/predictions",
        json={
            "lottery_id": 1,
            "strategy": "balanceado",
            "prediction_count": 1,
            "temperature": 0.2,
            "min_confidence_threshold": 60,
            "include_extra_number": False,
        },
    )

    assert response.status_code == 403
