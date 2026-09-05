import asyncio

from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.db.session import get_db
from app.main import app, unhandled_exception_handler
from app.services.lottery_draw_service import LotteryDrawService
from app.services.lottery_service import LotteryService

client = TestClient(app)


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_health_reports_database_failure(monkeypatch):
    def failing_execute(*args, **kwargs):
        raise SQLAlchemyError("database unavailable")

    db = next(get_db())
    monkeypatch.setattr(db, "execute", failing_execute)
    app.dependency_overrides[get_db] = lambda: db
    try:
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unhealthy",
            "service": "Lotto Analítica AI",
        }
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_health_reports_redis_failure_in_production(monkeypatch):
    original_environment = settings.environment
    original_health_check = login_rate_limiter.health_check
    try:
        settings.environment = "production"
        monkeypatch.setattr(
            login_rate_limiter,
            "health_check",
            lambda: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
        )
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {
            "status": "unhealthy",
            "service": "Lotto Analítica AI",
        }
    finally:
        settings.environment = original_environment
        monkeypatch.setattr(
            login_rate_limiter,
            "health_check",
            original_health_check,
        )


def test_security_headers():
    response = client.get("/health")

    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Permissions-Policy"] == (
        "geolocation=(), microphone=(), camera=()"
    )
    assert "Set-Cookie" not in response.headers


def test_auth_responses_are_not_cacheable():
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate"
    assert response.headers["Pragma"] == "no-cache"


def test_cors_allows_configured_frontend_origin():
    response = client.options(
        "/api/v1/lotteries",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert "GET" in response.headers["Access-Control-Allow-Methods"]
    assert response.headers.get("Access-Control-Allow-Credentials") != "true"


def test_cors_rejects_unconfigured_origin():
    response = client.options(
        "/api/v1/lotteries",
        headers={
            "Origin": "https://evil.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers


def test_cors_rejects_unconfigured_http_method():
    response = client.options(
        "/api/v1/lotteries",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "PATCH",
        },
    )

    assert response.status_code == 400
    assert "PATCH" not in response.headers["Access-Control-Allow-Methods"]


def test_cors_rejects_credentials_for_preflight():
    response = client.options(
        "/api/v1/lotteries",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.headers.get("Access-Control-Allow-Credentials") != "true"


def test_hsts_is_enabled_only_in_production(monkeypatch):
    original_environment = settings.environment
    try:
        settings.environment = "production"
        monkeypatch.setattr(login_rate_limiter, "health_check", lambda: None)
        production_response = client.get("/health")
        assert production_response.headers["Strict-Transport-Security"] == (
            "max-age=31536000; includeSubDomains"
        )

        settings.environment = "development"
        development_response = client.get("/health")
        assert "Strict-Transport-Security" not in development_response.headers
    finally:
        settings.environment = original_environment


def test_trusted_host_rejects_unapproved_host():
    response = client.get("/health", headers={"host": "evil.example"})

    assert response.status_code == 400


def test_trusted_host_allows_local_test_host():
    response = client.get("/health", headers={"host": "testserver"})

    assert response.status_code == 200


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


def test_unsupported_methods_return_405():
    response = client.patch("/api/v1/lotteries")
    assert response.status_code == 405

    response = client.patch("/api/v1/draws")
    assert response.status_code == 405

    response = client.post("/health")
    assert response.status_code == 405


def test_protected_lottery_mutations_require_authentication():
    assert client.post("/api/v1/lotteries").status_code == 401
    assert client.put("/api/v1/lotteries/1").status_code == 401
    assert client.delete("/api/v1/lotteries/1").status_code == 401


def test_protected_draw_mutations_require_authentication():
    assert client.post("/api/v1/draws").status_code == 401
    assert client.put("/api/v1/draws/1").status_code == 401
    assert client.delete("/api/v1/draws/1").status_code == 401


def test_protected_read_endpoints_require_authentication(monkeypatch):
    monkeypatch.setattr(LotteryService, "list_lotteries", lambda **kwargs: [])
    monkeypatch.setattr(LotteryDrawService, "list_draws", lambda **kwargs: [])

    lotteries_response = client.get("/api/v1/lotteries")
    draws_response = client.get("/api/v1/draws")

    assert lotteries_response.status_code == 401
    assert draws_response.status_code == 401
