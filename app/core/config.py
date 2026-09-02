from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Lotto Analítica AI"
    app_version: str = "0.1.0"
    environment: str = "development"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str = Field(min_length=32)
    allow_initial_registration: bool = False
    cors_allowed_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if self.environment == "development" and not self.cors_allowed_origins:
            self.cors_allowed_origins = [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
            ]

        if self.environment == "production":
            if self.allow_initial_registration:
                raise ValueError(
                    "ALLOW_INITIAL_REGISTRATION must be false in production"
                )
            if not self.cors_allowed_origins:
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS must be configured in production"
                )

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
