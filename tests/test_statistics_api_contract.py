from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app

client = TestClient(app)


def test_statistical_overview_contract_accepts_omitted_scope_for_compatibility():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role="admin", is_active=True
    )
    try:
        response = client.get("/api/v1/statistics/overview")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 200


def test_statistical_overview_accepts_source_scope():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role="admin", is_active=True
    )
    try:
        response = client.get("/api/v1/statistics/overview?source=baloto-colombia")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 200


def test_statistical_overview_rejects_non_positive_scope():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role="admin", is_active=True
    )
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=0")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 422


def test_statistical_overview_rejects_non_integer_scope():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, role="admin", is_active=True
    )
    try:
        response = client.get("/api/v1/statistics/overview?lottery_id=abc")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous
    assert response.status_code == 422
