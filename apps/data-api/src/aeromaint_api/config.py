from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
