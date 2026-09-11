from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.core.rate_limit import login_rate_limiter
from app.db.session import get_db
from app.main import app

client = TestClient(app)


def test_production_health_requires_redis_after_database_is_healthy(monkeypatch):
    original_environment = settings.environment
    try:
        settings.environment = "production"
        calls = []
        monkeypatch.setattr(login_rate_limiter, "health_check", lambda: calls.append("redis-ping"))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy", "service": "Lotto Analítica AI"}
        assert calls == ["redis-ping"]
    finally:
        settings.environment = original_environment


def test_nonproduction_health_skips_redis_dependency(monkeypatch):
    original_environment = settings.environment
    try:
        settings.environment = "test"
        calls = []
        monkeypatch.setattr(login_rate_limiter, "health_check", lambda: calls.append("unexpected"))
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert calls == []
    finally:
        settings.environment = original_environment


def test_production_health_fails_closed_when_redis_is_unavailable(monkeypatch):
    original_environment = settings.environment
    try:
        settings.environment = "production"
        monkeypatch.setattr(
            login_rate_limiter,
            "health_check",
            lambda: (_ for _ in ()).throw(RuntimeError("redis unavailable")),
        )
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "service": "Lotto Analítica AI"}
    finally:
        settings.environment = original_environment


def test_database_failure_short_circuits_production_health(monkeypatch):
    original_environment = settings.environment
    db = next(get_db())

    def failing_execute(*args, **kwargs):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(db, "execute", failing_execute)
    app.dependency_overrides[get_db] = lambda: db
    calls = []
    try:
        settings.environment = "production"
        monkeypatch.setattr(login_rate_limiter, "health_check", lambda: calls.append("unexpected"))
        response = client.get("/health")
        assert response.status_code == 503
        assert response.json() == {"status": "unhealthy", "service": "Lotto Analítica AI"}
        assert calls == []
    finally:
        settings.environment = original_environment
        app.dependency_overrides.clear()
        db.close()
