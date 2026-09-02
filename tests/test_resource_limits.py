from app.core.config import settings
from app.core.rate_limit import LoginRateLimiter
from app.db.session import engine


def test_database_pool_has_bounded_resource_settings():
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 10
    assert settings.database_pool_timeout == 10
    assert settings.database_pool_recycle == 1800
    assert engine.pool._pre_ping is True


def test_redis_client_has_bounded_socket_timeouts():
    client = LoginRateLimiter()._redis

    assert client.connection_pool.connection_kwargs["socket_connect_timeout"] == 5.0
    assert client.connection_pool.connection_kwargs["socket_timeout"] == 5.0
    assert client.connection_pool.connection_kwargs["health_check_interval"] == 30
