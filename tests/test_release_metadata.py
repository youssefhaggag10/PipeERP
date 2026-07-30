from pathlib import Path

from app.core.config import AppConfig
from app.database.migrations import DATABASE_VERSION, LATEST_SCHEMA_VERSION
from app.database.partner_opening_balance_schema import (
    DATABASE_VERSION as PARTNER_OPENING_BALANCE_DATABASE_VERSION,
)
from app.database.partner_opening_balance_schema import (
    SCHEMA_VERSION as PARTNER_OPENING_BALANCE_SCHEMA_VERSION,
)
from app.database.sales_finance_v10_schema import (
    DATABASE_VERSION as SALES_FINANCE_DATABASE_VERSION,
)
from app.database.sales_finance_v10_schema import (
    SCHEMA_VERSION as SALES_FINANCE_SCHEMA_VERSION,
)


def test_release_versions_are_consistent() -> None:
    project_root = Path(__file__).resolve().parents[1]
    pyproject = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    installer = (project_root / "installer" / "PipeERP.iss").read_text(encoding="utf-8")
    release_notes = (project_root / "docs" / "RELEASE_NOTES.md").read_text(
        encoding="utf-8"
    )

    assert AppConfig.APP_VERSION == "0.3.0"
    assert 'version = "0.3.0"' in pyproject
    assert '#define MyAppVersion "0.3.0"' in installer
    assert "OutputBaseFilename=PipeERP-Setup-{#MyAppVersion}" in installer
    assert "# PipeERP v0.3.0" in release_notes
    assert DATABASE_VERSION == "0.9.0"
    assert LATEST_SCHEMA_VERSION == 9
    assert SALES_FINANCE_DATABASE_VERSION == "0.10.0"
    assert SALES_FINANCE_SCHEMA_VERSION == 10
    assert PARTNER_OPENING_BALANCE_DATABASE_VERSION == "0.11.0"
    assert PARTNER_OPENING_BALANCE_SCHEMA_VERSION == 11
