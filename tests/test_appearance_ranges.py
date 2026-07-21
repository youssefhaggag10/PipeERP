from pathlib import Path

from app.database.connection import Database
from app.database.schema import initialize_database
from app.ui.appearance import AppearanceSettings, AppearanceSettingsRepository
from app.ui.styles import (
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    SCALE_PERCENT_MAX,
    SCALE_PERCENT_MIN,
    build_stylesheet,
)


def test_appearance_repository_preserves_full_supported_range(tmp_path: Path) -> None:
    database = Database(tmp_path / "appearance.sqlite3")
    initialize_database(database)
    repository = AppearanceSettingsRepository(database)

    minimum = AppearanceSettings(
        theme="dark",
        font_size=FONT_SIZE_MIN,
        scale_percent=SCALE_PERCENT_MIN,
    )
    repository.save_settings(minimum)
    assert repository.get_settings() == minimum

    maximum = AppearanceSettings(
        theme="light",
        font_size=FONT_SIZE_MAX,
        scale_percent=SCALE_PERCENT_MAX,
    )
    repository.save_settings(maximum)
    assert repository.get_settings() == maximum


def test_stylesheet_uses_small_and_large_user_values_without_old_clamps() -> None:
    small = build_stylesheet(
        "dark",
        font_size=FONT_SIZE_MIN,
        scale_percent=SCALE_PERCENT_MIN,
    )
    large = build_stylesheet(
        "light",
        font_size=FONT_SIZE_MAX,
        scale_percent=SCALE_PERCENT_MAX,
    )

    assert f"font-size: {FONT_SIZE_MIN}px;" in small
    assert f"font-size: {FONT_SIZE_MAX}px;" in large
    assert "min-height: 14px;" in small
    assert "min-height: 136px;" in large
