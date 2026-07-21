from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.database.connection import Database
from app.ui.styles import (
    FONT_SIZE_MAX,
    FONT_SIZE_MIN,
    SCALE_PERCENT_MAX,
    SCALE_PERCENT_MIN,
    build_stylesheet,
)

if TYPE_CHECKING:
    from PySide6.QtWidgets import QApplication

THEME_LABELS = {
    "dark": "داكن",
    "light": "فاتح",
    "system": "حسب إعداد ويندوز",
}


@dataclass(frozen=True)
class AppearanceSettings:
    theme: str = "dark"
    font_size: int = 13
    scale_percent: int = 100


class AppearanceSettingsRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def get_settings(self) -> AppearanceSettings:
        rows = self.database.fetch_all(
            "SELECT key, value FROM settings WHERE key IN (?, ?, ?)",
            ("appearance_theme", "appearance_font_size", "appearance_scale_percent"),
        )
        values = {str(row["key"]): str(row["value"]) for row in rows}
        theme = values.get("appearance_theme", "dark").strip().lower()
        if theme not in THEME_LABELS:
            theme = "dark"
        try:
            font_size = int(values.get("appearance_font_size", "13"))
        except ValueError:
            font_size = 13
        try:
            scale_percent = int(values.get("appearance_scale_percent", "100"))
        except ValueError:
            scale_percent = 100
        return AppearanceSettings(
            theme=theme,
            font_size=max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, font_size)),
            scale_percent=max(
                SCALE_PERCENT_MIN,
                min(SCALE_PERCENT_MAX, scale_percent),
            ),
        )

    def save_settings(self, settings: AppearanceSettings) -> None:
        if settings.theme not in THEME_LABELS:
            raise ValueError("اختيار الثيم غير صحيح")
        font_size = max(FONT_SIZE_MIN, min(FONT_SIZE_MAX, int(settings.font_size)))
        scale_percent = max(
            SCALE_PERCENT_MIN,
            min(SCALE_PERCENT_MAX, int(settings.scale_percent)),
        )
        with self.database.session(immediate=True) as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                (
                    ("appearance_theme", settings.theme),
                    ("appearance_font_size", str(font_size)),
                    ("appearance_scale_percent", str(scale_percent)),
                ),
            )


def _system_is_dark(app: QApplication) -> bool:
    from PySide6.QtCore import Qt

    try:
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except (AttributeError, TypeError):
        return app.palette().window().color().lightness() < 128


def apply_appearance(
    app: QApplication,
    repository: AppearanceSettingsRepository,
) -> AppearanceSettings:
    settings = repository.get_settings()
    resolved_theme = settings.theme
    if resolved_theme == "system":
        resolved_theme = "dark" if _system_is_dark(app) else "light"
    app.setStyle("Fusion")
    app.setStyleSheet(
        build_stylesheet(
            resolved_theme,
            font_size=settings.font_size,
            scale_percent=settings.scale_percent,
        )
    )
    return settings


__all__ = [
    "AppearanceSettings",
    "AppearanceSettingsRepository",
    "FONT_SIZE_MAX",
    "FONT_SIZE_MIN",
    "SCALE_PERCENT_MAX",
    "SCALE_PERCENT_MIN",
    "THEME_LABELS",
    "apply_appearance",
]
