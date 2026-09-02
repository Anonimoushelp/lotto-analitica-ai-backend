from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_security_headers():
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == (
        "geolocation=(), microphone=(), camera=()"
    )


def test_root_does_not_expose_environment():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "app": "Lotto Analítica AI",
        "version": "0.1.0",
        "status": "online",
    }


def test_openapi_documentation_matches_environment():
    response = client.get("/docs")

    if settings.environment.lower() == "development":
        assert response.status_code == 200
    else:
        assert response.status_code == 404


def test_openapi_json_matches_environment():
    response = client.get("/openapi.json")

    if settings.environment.lower() == "development":
        assert response.status_code == 200
    else:
        assert response.status_code == 404
