from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine_kwargs = {
    "pool_pre_ping": True,
    "pool_size": settings.database_pool_size,
    "max_overflow": settings.database_max_overflow,
    "pool_timeout": settings.database_pool_timeout,
    "pool_recycle": settings.database_pool_recycle,
}

if not settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {
        "connect_timeout": settings.database_connect_timeout,
    }

postgresql_url = settings.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
engine = create_engine(postgresql_url, **engine_kwargs)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
