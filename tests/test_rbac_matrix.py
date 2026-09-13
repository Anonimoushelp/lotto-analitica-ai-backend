from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app

client = TestClient(app)

READ_ENDPOINTS = [
    ("get", "/api/v1/lotteries"),
    ("get", "/api/v1/lotteries/1"),
    ("get", "/api/v1/draws"),
    ("get", "/api/v1/draws/1"),
    ("get", "/api/v1/statistics/overview"),
    ("get", "/api/v1/predictions/model-status"),
    ("get", "/api/v1/functional-encryption/status"),
    ("get", "/api/v1/tee/status"),
]

ADMIN_ONLY_ENDPOINTS = [
    ("post", "/api/v1/lotteries", {"code": "RBAC", "name": "RBAC", "country": "CO"}),
    ("put", "/api/v1/lotteries/1", {"name": "RBAC"}),
    ("delete", "/api/v1/lotteries/1", None),
    (
        "post",
        "/api/v1/draws",
        {
            "lottery_id": 1,
            "draw_number": "RBAC-1",
            "draw_date": "2026-01-01",
            "main_numbers": [1],
        },
    ),
    ("put", "/api/v1/draws/1", {"draw_number": "RBAC-2"}),
    ("delete", "/api/v1/draws/1", None),
    ("patch", "/api/v1/auth/admin/users/1", {"is_active": True}),
]


def set_user(role: str) -> None:
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        role=role,
        is_active=True,
        session_version=0,
    )


@pytest.fixture(autouse=True)
def clean_user_override():
    previous = app.dependency_overrides.get(get_current_user)
    yield
    if previous is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = previous


def request(method: str, path: str, payload=None):
    return (
        getattr(client, method)(path, json=payload)
        if payload is not None
        else getattr(client, method)(path)
    )


@pytest.mark.parametrize("method,path", READ_ENDPOINTS)
def test_all_protected_reads_require_authentication(method, path):
    response = request(method, path)
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["X-Request-ID"]


@pytest.mark.parametrize("role", ["viewer", "service", "user", "unknown"])
@pytest.mark.parametrize("method,path", READ_ENDPOINTS)
def test_non_analyst_roles_cannot_access_analyst_reads(role, method, path):
    set_user(role)
    response = request(method, path)
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    assert response.headers["X-Request-ID"]


@pytest.mark.parametrize("role", ["analyst", "viewer", "service", "user", "unknown"])
@pytest.mark.parametrize("method,path,payload", ADMIN_ONLY_ENDPOINTS)
def test_non_admin_roles_cannot_execute_admin_mutations(role, method, path, payload):
    set_user(role)
    response = request(method, path, payload)
    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient permissions"
    assert response.headers["X-Request-ID"]


def test_admin_role_is_accepted_by_role_guard():
    from app.api.dependencies.auth import require_admin, require_admin_or_analyst

    admin = SimpleNamespace(id=1, role="admin", is_active=True)
    assert require_admin(admin) is admin
    assert require_admin_or_analyst(admin) is admin


def test_analyst_role_is_accepted_only_by_read_analytics_guard():
    from app.api.dependencies.auth import require_admin, require_admin_or_analyst

    analyst = SimpleNamespace(id=2, role="analyst", is_active=True)
    assert require_admin_or_analyst(analyst) is analyst
    with pytest.raises(Exception) as exc_info:
        require_admin(analyst)
    assert exc_info.value.status_code == 403


def test_audit_mutation_is_not_reached_when_admin_guard_denies(monkeypatch):
    import app.api.routes.lotteries as lotteries_route

    called = False

    def fail_audit(*args, **kwargs):
        nonlocal called
        called = True
        raise AssertionError("audit must not run for denied mutation")

    monkeypatch.setattr(lotteries_route, "log_mutation", fail_audit)
    set_user("analyst")
    response = client.post(
        "/api/v1/lotteries",
        json={"code": "RBAC2", "name": "RBAC2", "country": "CO"},
    )
    assert response.status_code == 403
    assert called is False
