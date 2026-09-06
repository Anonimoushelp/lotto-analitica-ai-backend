import pytest
from pydantic import ValidationError

from app.core.config import Settings


BASE_PRODUCTION_SETTINGS = {
    "environment": "production",
    "database_url": "postgresql+psycopg://user:password@db.example.com/app?sslmode=require",
    "secret_key": "production-test-secret-key-with-at-least-32-chars",
    "redis_url": "rediss://redis.example.com:6379/0",
    "cors_allowed_origins": ["https://app.example.com"],
    "trusted_hosts": ["api.example.com"],
}


def test_production_settings_accept_explicit_cors_and_trusted_hosts():
    settings = Settings(**BASE_PRODUCTION_SETTINGS)

    assert settings.cors_allowed_origins == ["https://app.example.com"]
    assert settings.trusted_hosts == ["api.example.com"]


@pytest.mark.parametrize(
    "field,value,expected_message",
    [
        (
            "cors_allowed_origins",
            ["*"],
            "CORS_ALLOWED_ORIGINS cannot contain '*' in production",
        ),
        (
            "trusted_hosts",
            ["*"],
            "TRUSTED_HOSTS cannot contain '*' in production",
        ),
    ],
)
def test_production_settings_reject_wildcards(field, value, expected_message):
    config = {**BASE_PRODUCTION_SETTINGS, field: value}

    with pytest.raises(ValidationError, match=expected_message):
        Settings(**config)
