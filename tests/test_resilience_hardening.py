import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.rate_limit import LoginRateLimiter


def production_settings(**overrides):
    values = {
        "DATABASE_URL": "postgresql+psycopg://user:password@db.example/lotto?sslmode=verify-full",
        "SECRET_KEY": "x" * 32,
        "ENVIRONMENT": "production",
        "REDIS_URL": "rediss://:password@redis.example:6380/0",
        "CORS_ALLOWED_ORIGINS": ["https://app.example.com"],
        "TRUSTED_HOSTS": ["app.example.com"],
    }
    values.update(overrides)
    return Settings(**values)


def test_production_database_pool_bounds_are_validated():
    settings = production_settings(DATABASE_POOL_SIZE=50, DATABASE_MAX_OVERFLOW=100)

    assert settings.database_pool_size == 50
    assert settings.database_max_overflow == 100


@pytest.mark.parametrize(
    "field,value",
    [
        ("DATABASE_POOL_SIZE", 0),
        ("DATABASE_POOL_SIZE", 51),
        ("DATABASE_MAX_OVERFLOW", -1),
        ("DATABASE_MAX_OVERFLOW", 101),
        ("DATABASE_POOL_TIMEOUT", 0),
        ("DATABASE_POOL_TIMEOUT", 121),
        ("DATABASE_POOL_RECYCLE", 59),
        ("DATABASE_POOL_RECYCLE", 86401),
        ("DATABASE_CONNECT_TIMEOUT", 0),
        ("DATABASE_CONNECT_TIMEOUT", 61),
    ],
)
def test_database_pool_and_connection_limits_reject_unsafe_values(field, value):
    with pytest.raises(ValidationError):
        production_settings(**{field: value})


def test_production_requires_secure_redis_transport():
    with pytest.raises(ValidationError, match="REDIS_URL"):
        production_settings(REDIS_URL="redis://redis.example:6379/0")


def test_production_accepts_railway_private_redis_networking():
    settings = production_settings(REDIS_URL="redis://redis.railway.internal:6379/0")

    assert settings.redis_url.startswith("redis://")


def test_login_rate_limiter_hashes_sensitive_key_material():
    key = LoginRateLimiter._key("account", "user@example.com")

    assert "user@example.com" not in key
    assert key.startswith("auth:login:account:")
    assert len(key.rsplit(":", 1)[-1]) == 64


def test_login_rate_limiter_hashes_ip_key_material():
    key = LoginRateLimiter._key("ip", "192.0.2.10")

    assert "192.0.2.10" not in key
    assert key.startswith("auth:login:ip:")
    assert len(key.rsplit(":", 1)[-1]) == 64


def test_login_rate_limiter_keys_are_stable_and_distinct():
    first = LoginRateLimiter._key("account", "user@example.com")
    same = LoginRateLimiter._key("account", "user@example.com")
    different = LoginRateLimiter._key("account", "other@example.com")

    assert first == same
    assert first != different
