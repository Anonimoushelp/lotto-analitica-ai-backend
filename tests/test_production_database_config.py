import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_requires_postgresql_database():
    with pytest.raises(ValidationError, match="DATABASE_URL must use PostgreSQL in production"):
        Settings(
            database_url="sqlite:///./production.db",
            secret_key="ci-test-secret-key-with-at-least-32-characters",
            environment="production",
            cors_allowed_origins=["https://app.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_production_accepts_postgresql_database():
    settings = Settings(
        database_url="postgresql+psycopg://user:password@db.example.com/lotto?sslmode=require",
        secret_key="ci-test-secret-key-with-at-least-32-characters",
        environment="production",
        cors_allowed_origins=["https://app.example.com"],
        trusted_hosts=["api.example.com"],
    )

    assert settings.database_url.startswith("postgresql")


def test_non_production_can_use_sqlite_database():
    settings = Settings(
        database_url="sqlite:///./test.db",
        secret_key="ci-test-secret-key-with-at-least-32-characters",
        environment="test",
    )

    assert settings.database_url.startswith("sqlite")
