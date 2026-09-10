from app.core.config import settings
from app.db.session import engine, engine_kwargs


def test_database_engine_enables_pre_ping_and_bounded_pool():
    assert engine_kwargs["pool_pre_ping"] is True
    assert engine_kwargs["pool_size"] == settings.database_pool_size
    assert engine_kwargs["max_overflow"] == settings.database_max_overflow
    assert engine_kwargs["pool_timeout"] == settings.database_pool_timeout
    assert engine_kwargs["pool_recycle"] == settings.database_pool_recycle


def test_database_engine_uses_postgresql_connection_timeout():
    if settings.database_url.startswith("sqlite"):
        return
    assert engine_kwargs["connect_args"] == {"connect_timeout": settings.database_connect_timeout}
    assert engine.pool.size() == settings.database_pool_size
    assert engine.pool._max_overflow == settings.database_max_overflow
    assert engine.pool._timeout == settings.database_pool_timeout
