from urllib.parse import parse_qs, urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Lotto Analítica AI"
    app_version: str = "0.1.0"
    environment: str = "development"

    database_url: str
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=10, ge=0, le=100)
    database_pool_timeout: int = Field(default=10, ge=1, le=120)
    database_pool_recycle: int = Field(default=1800, ge=60, le=86400)
    database_connect_timeout: int = Field(default=5, ge=1, le=60)
    redis_url: str = "redis://localhost:6379/0"
    redis_connect_timeout: float = Field(default=5.0, gt=0, le=60)
    redis_socket_timeout: float = Field(default=5.0, gt=0, le=60)
    redis_health_check_interval: int = Field(default=30, ge=0, le=3600)

    secret_key: str = Field(min_length=32)
    gemini_api_key: str = ""
    allow_initial_registration: bool = False
    cors_allowed_origins: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        self.environment = self.environment.strip().lower()

        allowed_environments = {"development", "test", "production"}
        if self.environment not in allowed_environments:
            raise ValueError(
                "ENVIRONMENT must be one of: development, test, production"
            )

        if self.environment != "production":
            if not self.cors_allowed_origins:
                self.cors_allowed_origins = [
                    "http://localhost:3000",
                    "http://localhost:3001",
                    "http://127.0.0.1:3000",
                    "http://127.0.0.1:3001",
                ]
            if not self.trusted_hosts:
                self.trusted_hosts = [
                    "localhost",
                    "127.0.0.1",
                    "testserver",
                ]

        if self.environment == "production":
            if not self.database_url.startswith("postgresql"):
                raise ValueError(
                    "DATABASE_URL must use PostgreSQL in production"
                )

            database_query = parse_qs(urlparse(self.database_url).query)
            sslmode = database_query.get("sslmode", [""])[0].lower()
            if sslmode not in {"require", "verify-ca", "verify-full"}:
                raise ValueError(
                    "DATABASE_URL must require PostgreSQL TLS in production"
                )

            redis = urlparse(self.redis_url)
            redis_host = (redis.hostname or "").lower().rstrip(".")
            redis_is_tls = redis.scheme == "rediss"
            redis_is_railway_private = redis.scheme == "redis" and (
                redis_host == "railway.internal"
                or redis_host.endswith(".railway.internal")
            )
            if not (redis_is_tls or redis_is_railway_private):
                raise ValueError(
                    "REDIS_URL must use TLS or Railway private networking in production"
                )

            if self.allow_initial_registration:
                raise ValueError(
                    "ALLOW_INITIAL_REGISTRATION must be false in production"
                )
            if not self.cors_allowed_origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must be configured in production"
                )
            if not self.trusted_hosts:
                raise ValueError(
                    "TRUSTED_HOSTS must be configured in production"
                )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
