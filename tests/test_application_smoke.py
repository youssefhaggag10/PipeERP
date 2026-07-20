import os
from pathlib import Path

import pytest

if os.environ.get("PIPEERP_GUI_SMOKE") != "1":
    pytest.skip("GUI smoke tests run in the dedicated offscreen workflow", allow_module_level=True)


def test_offscreen_themes_and_core_windows_open_without_crash(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from app.database.connection import Database
    from app.database.schema import initialize_database
    from app.services.auth_service import AuthService
    from app.services.first_run_service import FirstRunService
    from app.ui.appearance import AppearanceSettings, AppearanceSettingsRepository, apply_appearance
    from app.ui.main_window import MainWindow

    database = Database(tmp_path / "gui-smoke.sqlite3")
    initialize_database(database)
    FirstRunService(database).create_initial_admin(
        username="smoke_admin",
        full_name="Smoke Admin",
        password="Smoke-Test-123",
    )
    user = AuthService(database).authenticate("smoke_admin", "Smoke-Test-123")
    assert user is not None

    app = QApplication.instance() or QApplication([])
    appearance = AppearanceSettingsRepository(database)
    for theme in ("dark", "light", "system"):
        expected = AppearanceSettings(theme=theme, font_size=14, scale_percent=110)
        appearance.save_settings(expected)
        assert apply_appearance(app, appearance) == expected
        assert app.styleSheet().strip()

    window = MainWindow(user, database)
    window.show()
    app.processEvents()

    expected_pages = {
        "الرئيسية",
        "CRM متابعة العملاء",
        "الأصناف",
        "المبيعات",
        "التصنيع",
        "الإعدادات",
    }
    assert expected_pages.issubset(window.page_indexes)
    for title in expected_pages:
        index = window.page_indexes[title]
        window.navigation.setCurrentRow(index)
        app.processEvents()
        assert window.pages.widget(index) is not None

    window.close()
    app.processEvents()
