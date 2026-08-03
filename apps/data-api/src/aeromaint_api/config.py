from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AEROMAINT_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    api_host: str = "0.0.0.0"  # noqa: S104 - container binding is intentional
    api_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
