from pathlib import Path

from pydantic import ValidationError
from pytest import MonkeyPatch, raises

from app.core.settings import Settings


def test_allowed_origins_accepts_single_origin_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:5173")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.allowed_origins == ["http://localhost:5173"]


def test_allowed_origins_accepts_comma_separated_environment_value(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "s" * 32)
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "https://erp.example.com, https://admin.example.com",
    )

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.allowed_origins == [
        "https://erp.example.com",
        "https://admin.example.com",
    ]


def test_secrets_can_be_loaded_from_compose_secret_files(
    monkeypatch: MonkeyPatch, tmp_path: Path
) -> None:
    database_file = tmp_path / "database_url"
    secret_file = tmp_path / "secret_key"
    database_file.write_text("postgresql+psycopg://pipeerp@database/pipeerp\n", encoding="utf-8")
    secret_file.write_text("x" * 48 + "\n", encoding="utf-8")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("DATABASE_URL_FILE", str(database_file))
    monkeypatch.setenv("SECRET_KEY_FILE", str(secret_file))

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database_url == "postgresql+psycopg://pipeerp@database/pipeerp"
    assert settings.secret_key == "x" * 48


def test_production_rejects_http_origins_and_placeholder_secrets(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pipeerp@database/pipeerp")
    monkeypatch.setenv("SECRET_KEY", "replace-with-a-production-secret-key-value")
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://erp.example.com")

    with raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
