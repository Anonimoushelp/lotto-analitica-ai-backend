import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.rate_limit import AiRateLimiter, LoginRateLimiter
from app.models.lottery_draw import LotteryDraw
from app.repositories.lottery_draw_repository import LotteryDrawRepository


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("CORS_ALLOWED_ORIGINS", ["*"]),
        ("CORS_ALLOWED_ORIGINS", ["http://app.example.com"]),
        ("CORS_ALLOWED_ORIGINS", ["https://app.example.com/api"]),
        ("CORS_ALLOWED_ORIGINS", ["https://user:password@app.example.com"]),
        ("TRUSTED_HOSTS", ["*"]),
        ("TRUSTED_HOSTS", ["https://app.example.com"]),
        ("TRUSTED_HOSTS", ["app.example.com:443"]),
        ("TRUSTED_HOSTS", ["*example.com"]),
    ],
)
def test_production_rejects_unsafe_network_allowlists(field, value):
    with pytest.raises(ValidationError):
        production_settings(**{field: value})


def test_production_accepts_valid_network_allowlist_patterns():
    settings = production_settings(
        CORS_ALLOWED_ORIGINS=["https://app.example.com", "https://admin.example.com"],
        TRUSTED_HOSTS=["app.example.com", "*.svc.example.com"],
    )

    assert len(settings.cors_allowed_origins) == 2
    assert settings.trusted_hosts == ["app.example.com", "*.svc.example.com"]


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


def test_ai_rate_limiter_hashes_user_identity():
    key = AiRateLimiter._key("12345")

    assert "12345" not in key
    assert key.startswith("ai:predictions:user:")
    assert len(key.rsplit(":", 1)[-1]) == 64


def test_rate_limiters_wire_redis_timeouts_and_health_check(monkeypatch):
    calls = []

    class FakeRedis:
        def ping(self):
            return True

    def fake_from_url(url, **kwargs):
        calls.append((url, kwargs))
        return FakeRedis()

    monkeypatch.setattr("app.core.rate_limit.redis.Redis.from_url", fake_from_url)

    settings = production_settings(
        REDIS_CONNECT_TIMEOUT=2.5,
        REDIS_SOCKET_TIMEOUT=7.5,
        REDIS_HEALTH_CHECK_INTERVAL=45,
    )
    monkeypatch.setattr("app.core.rate_limit.settings", settings)

    limiter = LoginRateLimiter()
    limiter.health_check()
    AiRateLimiter()

    assert len(calls) == 2
    for url, kwargs in calls:
        assert url == settings.redis_url
        assert kwargs == {
            "decode_responses": True,
            "socket_connect_timeout": 2.5,
            "socket_timeout": 7.5,
            "health_check_interval": 45,
        }


def test_redis_health_check_propagates_dependency_failure(monkeypatch):
    class FailingRedis:
        def ping(self):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(
        "app.core.rate_limit.redis.Redis.from_url",
        lambda url, **kwargs: FailingRedis(),
    )
    monkeypatch.setattr("app.core.rate_limit.settings", production_settings())

    limiter = LoginRateLimiter()

    with pytest.raises(ConnectionError, match="redis unavailable"):
        limiter.health_check()


def test_rate_limiter_does_not_fail_open_when_redis_is_unavailable(monkeypatch):
    class FailingRedis:
        def eval(self, *args, **kwargs):
            raise ConnectionError("redis unavailable")

    monkeypatch.setattr(
        "app.core.rate_limit.redis.Redis.from_url",
        lambda url, **kwargs: FailingRedis(),
    )
    monkeypatch.setattr("app.core.rate_limit.settings", production_settings())

    limiter = LoginRateLimiter()

    with pytest.raises(ConnectionError, match="redis unavailable"):
        limiter.allow("user@example.com", "192.0.2.10")


def test_draw_repository_create_rolls_back_on_database_failure():
    class FailingSession:
        def __init__(self):
            self.added = None
            self.rollback_called = False

        def add(self, value):
            self.added = value

        def commit(self):
            raise SQLAlchemyError("database unavailable")

        def rollback(self):
            self.rollback_called = True

        def refresh(self, value):
            raise AssertionError("refresh must not run after commit failure")

    db = FailingSession()
    draw = LotteryDraw(
        lottery_id=1,
        draw_number="RECOVERY-001",
        draw_date="2026-09-10",
        main_numbers=[1, 2, 3, 4, 5],
    )

    with pytest.raises(SQLAlchemyError):
        LotteryDrawRepository.create(db, draw)

    assert db.added is draw
    assert db.rollback_called is True


def test_draw_repository_delete_rolls_back_on_database_failure():
    class FailingSession:
        def __init__(self):
            self.deleted = None
            self.rollback_called = False

        def delete(self, value):
            self.deleted = value

        def commit(self):
            raise SQLAlchemyError("database unavailable")

        def rollback(self):
            self.rollback_called = True

    db = FailingSession()
    draw = LotteryDraw(id=1, lottery_id=1, draw_number="RECOVERY-002")

    with pytest.raises(SQLAlchemyError):
        LotteryDrawRepository.delete(db, draw)

    assert db.deleted is draw
    assert db.rollback_called is True
