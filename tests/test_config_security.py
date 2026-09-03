import pytest

from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "sqlite:///./test.db",
        "secret_key": "test-secret-key-with-at-least-32-characters",
    }
    values.update(overrides)
    return Settings(**values)


def test_production_environment_is_normalized_before_security_checks():
    configured = _settings(
        environment="  PrOdUcTiOn  ",
        database_url="postgresql://user:password@localhost:5432/lotto?sslmode=require",
        redis_url="rediss://localhost:6379/0",
        cors_allowed_origins=["https://api.example.com"],
        trusted_hosts=["api.example.com"],
    )

    assert configured.environment == "production"


def test_mixed_case_production_still_rejects_initial_registration():
    with pytest.raises(ValueError, match="ALLOW_INITIAL_REGISTRATION"):
        _settings(
            environment="Production",
            database_url="postgresql://user:password@localhost:5432/lotto?sslmode=require",
            redis_url="rediss://localhost:6379/0",
            allow_initial_registration=True,
            cors_allowed_origins=["https://api.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_mixed_case_production_requires_explicit_cors_and_trusted_hosts():
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        _settings(
            environment="PRODUCTION",
            database_url="postgresql://user:password@localhost:5432/lotto?sslmode=require",
            redis_url="rediss://localhost:6379/0",
        )

    with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
        _settings(
            environment="PRODUCTION",
            database_url="postgresql://user:password@localhost:5432/lotto?sslmode=require",
            redis_url="rediss://localhost:6379/0",
            cors_allowed_origins=["https://api.example.com"],
        )


def test_unknown_environment_value_fails_closed():
    with pytest.raises(ValueError, match="ENVIRONMENT must be one of"):
        _settings(environment="prod")


def test_production_requires_encrypted_postgresql_connection():
    with pytest.raises(ValueError, match="PostgreSQL TLS"):
        _settings(
            environment="production",
            database_url="postgresql://user:password@localhost:5432/lotto",
            redis_url="rediss://localhost:6379/0",
            cors_allowed_origins=["https://api.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_production_accepts_supported_postgresql_tls_modes():
    for sslmode in ("require", "verify-ca", "verify-full"):
        configured = _settings(
            environment="production",
            database_url=(
                "postgresql://user:password@localhost:5432/lotto"
                f"?sslmode={sslmode}"
            ),
            redis_url="rediss://localhost:6379/0",
            cors_allowed_origins=["https://api.example.com"],
            trusted_hosts=["api.example.com"],
        )
        assert configured.environment == "production"


def test_production_rejects_non_tls_postgresql_sslmode():
    with pytest.raises(ValueError, match="PostgreSQL TLS"):
        _settings(
            environment="production",
            database_url=(
                "postgresql://user:password@localhost:5432/lotto?sslmode=disable"
            ),
            redis_url="rediss://localhost:6379/0",
            cors_allowed_origins=["https://api.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_production_requires_encrypted_redis_connection():
    with pytest.raises(ValueError, match="REDIS_URL must use TLS"):
        _settings(
            environment="production",
            database_url="postgresql://user:password@localhost:5432/lotto?sslmode=require",
            redis_url="redis://localhost:6379/0",
            cors_allowed_origins=["https://api.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_production_accepts_tls_redis_connection():
    configured = _settings(
        environment="production",
        database_url="postgresql://user:password@localhost:5432/lotto?sslmode=require",
        redis_url="rediss://redis.example.com:6379/0",
        cors_allowed_origins=["https://api.example.com"],
        trusted_hosts=["api.example.com"],
    )

    assert configured.redis_url.startswith("rediss://")


def test_supported_non_production_environments_are_accepted():
    assert _settings(environment="development").environment == "development"
    assert _settings(environment="test").environment == "test"
