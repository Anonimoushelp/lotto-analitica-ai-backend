from app.core.config import settings
from app.core.rate_limit import AiRateLimiter, LoginRateLimiter


def test_login_rate_limiter_uses_memory_when_redis_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    limiter = LoginRateLimiter()

    assert [limiter.allow("user@example.com", "127.0.0.1") for _ in range(5)] == [
        True
    ] * 5
    assert limiter.allow("user@example.com", "127.0.0.1") is False

    limiter.reset("user@example.com", "127.0.0.1")
    assert limiter.allow("user@example.com", "127.0.0.1") is True


def test_login_rate_limiter_enforces_account_and_ip_windows_in_memory(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    limiter = LoginRateLimiter()

    for index in range(5):
        assert limiter.allow(f"user{index}@example.com", "127.0.0.1") is True

    assert limiter.allow("user5@example.com", "127.0.0.1") is True
    for index in range(14):
        assert limiter.allow(f"other{index}@example.com", "127.0.0.1") is True

    assert limiter.allow("other14@example.com", "127.0.0.1") is False


def test_ai_rate_limiter_uses_memory_when_redis_is_not_configured(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    limiter = AiRateLimiter()

    assert [limiter.allow(42) for _ in range(10)] == [True] * 10
    assert limiter.allow(42) is False


def test_rate_limit_health_check_is_noop_without_redis(monkeypatch):
    monkeypatch.setattr(settings, "redis_url", "")
    limiter = LoginRateLimiter()

    limiter.health_check()
