from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://localhost/pipeerp"
    secret_key: str = Field(min_length=32)
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    access_token_minutes: int = Field(default=15, ge=5, le=60)
    refresh_session_hours: int = Field(default=12, ge=1, le=72)
    login_lock_minutes: int = Field(default=15, ge=1, le=60)
    login_max_attempts: int = Field(default=5, ge=3, le=10)

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def expose_api_docs(self) -> bool:
        return self.app_env != "production"

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
