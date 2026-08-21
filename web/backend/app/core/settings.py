from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://localhost/pipeerp"
    database_url_file: str | None = None
    secret_key: str = Field(default="", min_length=32)
    secret_key_file: str | None = None
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]
    access_token_minutes: int = Field(default=15, ge=5, le=60)
    refresh_session_hours: int = Field(default=12, ge=1, le=72)
    login_lock_minutes: int = Field(default=15, ge=1, le=60)
    login_max_attempts: int = Field(default=5, ge=3, le=10)

    @model_validator(mode="before")
    @classmethod
    def load_file_secrets(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        for field_name in ("database_url", "secret_key"):
            file_name = data.get(f"{field_name}_file")
            if file_name and not data.get(field_name):
                try:
                    data[field_name] = Path(str(file_name)).read_text(encoding="utf-8").strip()
                except OSError as exc:
                    raise ValueError(f"تعذر قراءة ملف السر {field_name}") from exc
        return data

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.app_env != "production":
            return self
        if not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("الإنتاج يتطلب اتصال PostgreSQL عبر psycopg")
        if any(not origin.startswith("https://") for origin in self.allowed_origins):
            raise ValueError("أصول CORS في الإنتاج يجب أن تستخدم HTTPS فقط")
        lowered_secret = self.secret_key.casefold()
        if "change-this" in lowered_secret or "replace-with" in lowered_secret:
            raise ValueError("SECRET_KEY الإنتاجي ما زال قيمة افتراضية")
        return self

    @property
    def expose_api_docs(self) -> bool:
        return self.app_env != "production"

    @property
    def secure_cookies(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_regex(self) -> str | None:
        if self.app_env == "production":
            return None
        return (
            r"^https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
            r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
            r"(?::\d+)?$"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
