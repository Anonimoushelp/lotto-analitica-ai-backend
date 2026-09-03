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
        cors_allowed_origins=["https://api.example.com"],
        trusted_hosts=["api.example.com"],
    )

    assert configured.environment == "production"


def test_mixed_case_production_still_rejects_initial_registration():
    with pytest.raises(ValueError, match="ALLOW_INITIAL_REGISTRATION"):
        _settings(
            environment="Production",
            allow_initial_registration=True,
            cors_allowed_origins=["https://api.example.com"],
            trusted_hosts=["api.example.com"],
        )


def test_mixed_case_production_requires_explicit_cors_and_trusted_hosts():
    with pytest.raises(ValueError, match="CORS_ALLOWED_ORIGINS"):
        _settings(environment="PRODUCTION")

    with pytest.raises(ValueError, match="TRUSTED_HOSTS"):
        _settings(
            environment="PRODUCTION",
            cors_allowed_origins=["https://api.example.com"],
        )
