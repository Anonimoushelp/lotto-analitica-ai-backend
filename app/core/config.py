from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Lotto Analítica AI"
    app_version: str = "0.1.0"
    environment: str = "development"

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    secret_key: str
    cors_allowed_origins: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def configure_development_cors(self) -> "Settings":
        if self.environment == "development" and not self.cors_allowed_origins:
            self.cors_allowed_origins = [
    "http://localhost:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:3001",
]

        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
