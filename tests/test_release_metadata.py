from pathlib import Path

from app.core.config import AppConfig
from app.database.migrations import DATABASE_VERSION, LATEST_SCHEMA_VERSION


def test_release_versions_are_consistent() -> None:
    project_root = Path(__file__).resolve().parents[1]
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    installer = (project_root / "installer" / "PipeERP.iss").read_text(encoding="utf-8")

    assert AppConfig.APP_VERSION == "0.2.0"
    assert 'version = "0.2.0"' in pyproject
    assert '#define MyAppVersion "0.2.0"' in installer
    assert "OutputBaseFilename=PipeERP-Setup-{#MyAppVersion}" in installer
    assert DATABASE_VERSION == "0.9.0"
    assert LATEST_SCHEMA_VERSION == 9
