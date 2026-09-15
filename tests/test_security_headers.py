from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_security_headers_are_present_on_application_responses():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == (
        "geolocation=(), microphone=(), camera=()"
    )
    assert "Strict-Transport-Security" not in response.headers


def test_production_responses_include_hsts(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == (
        "max-age=31536000; includeSubDomains"
    )


def test_cors_preflight_allows_patch_for_admin_user_updates():
    client = TestClient(app)

    response = client.options(
        "/api/v1/auth/admin/users/1",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "PATCH" in response.headers["access-control-allow-methods"]
