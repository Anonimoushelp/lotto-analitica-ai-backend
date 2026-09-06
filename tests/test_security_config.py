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

    with pytest.raises(ValidationError) as exc_info:
        Settings(**config)

    assert expected_message in str(exc_info.value)


@pytest.mark.parametrize(
    "origin",
    [
        "http://app.example.com",
        "https://app.example.com/path",
        "https://user:password@app.example.com",
        "https://app.example.com?tenant=1",
        "https://app.example.com#fragment",
    ],
)
def test_production_settings_reject_insecure_or_malformed_cors_origins(origin):
    config = {**BASE_PRODUCTION_SETTINGS, "cors_allowed_origins": [origin]}

    with pytest.raises(ValidationError) as exc_info:
        Settings(**config)

    assert (
        "CORS_ALLOWED_ORIGINS must contain HTTPS origins without paths or credentials in production"
        in str(exc_info.value)
    )


def test_production_settings_accept_https_cors_origin_with_port():
    config = {**BASE_PRODUCTION_SETTINGS, "cors_allowed_origins": ["https://app.example.com:8443"]}

    settings = Settings(**config)

    assert settings.cors_allowed_origins == ["https://app.example.com:8443"]


@pytest.mark.parametrize(
    "host",
    [
        "https://api.example.com",
        "api.example.com:8443",
        "api.example.com/path",
        "user:password@api.example.com",
        "api.example.com?tenant=1",
        "api.example.com#fragment",
        "api.*.example.com",
        "*api.example.com",
        "*.",
    ],
)
def test_production_settings_reject_malformed_trusted_hosts(host):
    config = {**BASE_PRODUCTION_SETTINGS, "trusted_hosts": [host]}

    with pytest.raises(ValidationError) as exc_info:
        Settings(**config)

    assert (
        "TRUSTED_HOSTS must contain valid hostnames or *.subdomain patterns without ports or URL components in production"
        in str(exc_info.value)
    )


@pytest.mark.parametrize("host", ["api.example.com", "*.example.com", "192.0.2.10"])
def test_production_settings_accept_valid_trusted_hosts(host):
    config = {**BASE_PRODUCTION_SETTINGS, "trusted_hosts": [host]}

    settings = Settings(**config)

    assert settings.trusted_hosts == [host]
