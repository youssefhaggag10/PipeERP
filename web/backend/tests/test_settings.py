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
