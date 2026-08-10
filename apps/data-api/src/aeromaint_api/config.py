from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEVELOPMENT_JWT_SECRET = "development-only-change-me"  # noqa: S105 - local-only default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEROMAINT_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    api_host: str = "0.0.0.0"  # noqa: S104 - container binding is intentional
    api_port: int = 8000
    database_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AEROMAINT_DATABASE_URL", "DATABASE_URL"),
    )
    migrate_on_startup: bool = True
    jwt_secret: str = DEVELOPMENT_JWT_SECRET
    jwt_issuer: str = "aeromaint-local"
    jwt_audience: str = "aeromaint-api"
    rate_limit_requests: int = 120
    rate_limit_window_seconds: int = 60

    @model_validator(mode="after")
    def reject_development_secret_in_production(self) -> "Settings":
        if self.env == "production" and self.jwt_secret == DEVELOPMENT_JWT_SECRET:
            raise ValueError("AEROMAINT_JWT_SECRET must be configured in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
