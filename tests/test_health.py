import asyncio

from fastapi import Request
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app, unhandled_exception_handler

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


def test_hsts_is_enabled_only_in_production():
    original_environment = settings.environment
    try:
        settings.environment = "production"
        production_response = client.get("/health")
        assert production_response.headers["Strict-Transport-Security"] == (
            "max-age=31536000; includeSubDomains"
        )

        settings.environment = "development"
        development_response = client.get("/health")
        assert "Strict-Transport-Security" not in development_response.headers
    finally:
        settings.environment = original_environment


def test_root_does_not_expose_environment():
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "app": "Lotto Analítica AI",
        "version": "0.1.0",
        "status": "online",
    }


def test_unhandled_exception_handler_hides_internal_error_details():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/internal-test",
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    request = Request(scope)

    response = asyncio.run(
        unhandled_exception_handler(request, RuntimeError("secret internal detail"))
    )

    assert response.status_code == 500
    assert response.body == b'{"detail":"Internal server error"}'
    assert b"secret internal detail" not in response.body


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
