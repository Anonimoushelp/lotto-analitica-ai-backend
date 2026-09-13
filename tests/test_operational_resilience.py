from pytest import mark, raises
from pydantic import ValidationError

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


def test_operational_timeouts_have_safe_bounded_defaults():
    settings = Settings(**BASE_PRODUCTION)

    assert settings.database_pool_timeout == 10
    assert settings.database_connect_timeout == 5
    assert settings.database_pool_recycle == 1800
    assert settings.redis_connect_timeout == 5.0
    assert settings.redis_socket_timeout == 5.0
    assert settings.redis_health_check_interval == 30


@mark.parametrize(
    "field,value",
    [
        ("database_pool_timeout", 0),
        ("database_connect_timeout", 0),
        ("database_pool_recycle", 59),
        ("redis_connect_timeout", 0),
        ("redis_socket_timeout", 0),
        ("redis_health_check_interval", -1),
    ],
)
def test_operational_timeouts_reject_unsafe_values(field, value):
    with raises(ValidationError):
        Settings(**{**BASE_PRODUCTION, field: value})


def test_production_accepts_railway_private_redis_for_continuity():
    settings = Settings(
        **{**BASE_PRODUCTION, "redis_url": "redis://redis.railway.internal:6379/0"}
    )

    assert settings.redis_url.startswith("redis://")


def test_production_rejects_public_plaintext_redis():
    with raises(ValidationError, match="REDIS_URL must use TLS"):
        Settings(**{**BASE_PRODUCTION, "redis_url": "redis://redis.example.com:6379/0"})


def test_production_requires_database_tls_for_dependency_continuity():
    with raises(ValidationError, match="DATABASE_URL must require PostgreSQL TLS"):
        Settings(
            **{
                **BASE_PRODUCTION,
                "database_url": "postgresql+psycopg://user:password@db.example.com/app?sslmode=disable",
            }
        )
