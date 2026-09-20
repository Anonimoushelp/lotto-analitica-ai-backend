import logging

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_exposes_request_id_without_internal_dependencies():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
    assert response.json() == {
        "status": "healthy",
        "service": "Lotto Analítica AI",
    }
    assert "database" not in response.json()
    assert "redis" not in response.json()


def test_observability_log_contains_correlation_and_request_outcome(caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get("/health", headers={"X-Request-ID": "ops.request-123"})

    assert response.status_code == 200
    records = [record.getMessage() for record in caplog.records]
    completed = [message for message in records if message.startswith("request_completed")]
    assert completed
    assert "request_id=ops.request-123" in completed[-1]
    assert "method=GET" in completed[-1]
    assert "path=/health" in completed[-1]
    assert "status_code=200" in completed[-1]
    assert "duration_ms=" in completed[-1]


def test_observability_does_not_log_query_string_or_authorization_header(caplog):
    secret = "Bearer super-secret-token"
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get(
            "/health?secret=do-not-log",
            headers={
                "Authorization": secret,
                "X-Request-ID": "safe.request-456",
            },
        )

    assert response.status_code == 200
    combined_logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "do-not-log" not in combined_logs
    assert secret not in combined_logs
    assert "safe.request-456" in combined_logs


def test_not_found_is_observable_with_request_correlation(caplog):
    with caplog.at_level(logging.INFO, logger="app.main"):
        response = client.get(
            "/operationally-missing",
            headers={"X-Request-ID": "ops.not-found-789"},
        )

    assert response.status_code == 404
    assert response.headers["X-Request-ID"] == "ops.not-found-789"
    completed = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("request_completed")
    ]
    assert completed
    assert "request_id=ops.not-found-789" in completed[-1]
    assert "status_code=404" in completed[-1]


def test_health_remains_safe_when_internal_dependency_fails(monkeypatch):
    from app.core.config import settings
    from app.core.rate_limit import login_rate_limiter

    original_environment = settings.environment
    try:
        settings.environment = "production"
        monkeypatch.setattr(
            login_rate_limiter,
            "health_check",
            lambda: (_ for _ in ()).throw(RuntimeError("redis secret detail")),
        )
        response = client.get("/health")
    finally:
        settings.environment = original_environment

    assert response.status_code == 503
    assert response.json() == {
        "status": "unhealthy",
        "service": "Lotto Analítica AI",
    }
    assert "redis secret detail" not in response.text
