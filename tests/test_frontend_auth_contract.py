from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.dependencies.auth import get_current_user
from app.main import app

client = TestClient(app)


def test_frontend_auth_login_contract(monkeypatch):
    class FakeResult:
        def scalar(self, *_args, **_kwargs):
            return SimpleNamespace(
                id=7,
                email="analyst@example.com",
                password_hash="hashed",
                role="analyst",
                is_active=True,
                session_version=3,
            )

    class FakeDB:
        def scalar(self, *_args, **_kwargs):
            return FakeResult().scalar()

    monkeypatch.setattr("app.api.routes.auth.login_rate_limiter.allow", lambda *_: True)
    monkeypatch.setattr("app.api.routes.auth.login_rate_limiter.reset", lambda *_: None)
    monkeypatch.setattr("app.api.routes.auth.verify_password", lambda *_: True)
    monkeypatch.setattr(
        "app.api.routes.auth.create_access_token",
        lambda subject, role, session_version: "test-token",
    )
    app.dependency_overrides[__import__("app.db.session", fromlist=["get_db"]).get_db] = lambda: FakeDB()
    try:
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "analyst@example.com", "password": "correct-password"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"access_token": "test-token", "token_type": "bearer"}


def test_frontend_auth_me_preserves_user_contract():
    previous = app.dependency_overrides.get(get_current_user)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=7,
        email="analyst@example.com",
        role="analyst",
        is_active=True,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    try:
        response = client.get("/api/v1/auth/me", headers={"Accept": "application/json"})
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_current_user, None)
        else:
            app.dependency_overrides[get_current_user] = previous

    assert response.status_code == 200
    assert response.json() == {
        "id": 7,
        "email": "analyst@example.com",
        "role": "analyst",
        "is_active": True,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-02T00:00:00Z",
    }


def test_frontend_auth_login_validation_returns_json_422():
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": "short"},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()
