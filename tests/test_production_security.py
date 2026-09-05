from pydantic import ValidationError
import pytest

from app.core.config import Settings


BASE_PRODUCTION = {
    "environment": "production",
    "database_url": "postgresql+psycopg://user:password@db.example.com/app?sslmode=require",
    "redis_url": "rediss://redis.example.com:6379/0",
    "secret_key": "a" * 32,
    "cors_allowed_origins": ["https://lotto-analitica-ai.vercel.app"],
    "trusted_hosts": ["api.example.com"],
    "allow_initial_registration": False,
}


def test_production_settings_accept_secure_baseline():
    settings = Settings(**BASE_PRODUCTION)

    assert settings.environment == "production"
    assert settings.database_url.startswith("postgresql")
    assert "sslmode=require" in settings.database_url
    assert settings.redis_url.startswith("rediss://")
    assert settings.allow_initial_registration is False
    assert settings.cors_allowed_origins == ["https://lotto-analitica-ai.vercel.app"]
    assert settings.trusted_hosts == ["api.example.com"]


@pytest.mark.parametrize(
    "database_url",
    [
        "postgresql+psycopg://user:password@db.example.com/app",
        "postgresql+psycopg://user:password@db.example.com/app?sslmode=disable",
    ],
)
def test_production_rejects_database_without_tls(database_url):
    with pytest.raises(ValidationError, match="DATABASE_URL must require PostgreSQL TLS"):
        Settings(**{**BASE_PRODUCTION, "database_url": database_url})


def test_production_rejects_non_tls_redis():
    with pytest.raises(ValidationError, match="REDIS_URL must use TLS"):
        Settings(**{**BASE_PRODUCTION, "redis_url": "redis://redis.example.com:6379/0"})


def test_production_rejects_initial_registration():
    with pytest.raises(ValidationError, match="ALLOW_INITIAL_REGISTRATION must be false"):
        Settings(**{**BASE_PRODUCTION, "allow_initial_registration": True})


@pytest.mark.parametrize("field", ["cors_allowed_origins", "trusted_hosts"])
def test_production_requires_explicit_network_allowlists(field):
    values = {**BASE_PRODUCTION, field: []}
    message = "CORS_ALLOWED_ORIGINS must be configured" if field == "cors_allowed_origins" else "TRUSTED_HOSTS must be configured"

    with pytest.raises(ValidationError, match=message):
        Settings(**values)


def test_production_rejects_non_postgresql_database():
    with pytest.raises(ValidationError, match="DATABASE_URL must use PostgreSQL"):
        Settings(**{**BASE_PRODUCTION, "database_url": "sqlite:///./lotto.db"})


def test_secret_key_requires_minimum_length():
    with pytest.raises(ValidationError):
        Settings(**{**BASE_PRODUCTION, "secret_key": "short"})
