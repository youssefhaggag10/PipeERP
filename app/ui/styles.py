from __future__ import annotations

DARK_PALETTE = {
    "window": "#0F172A",
    "surface": "#111827",
    "surface_alt": "#020617",
    "surface_hover": "#172033",
    "border": "#334155",
    "border_soft": "#1F2937",
    "text": "#E5E7EB",
    "text_strong": "#F8FAFC",
    "text_muted": "#94A3B8",
    "primary": "#2563EB",
    "primary_hover": "#1D4ED8",
    "focus": "#38BDF8",
    "danger": "#DC2626",
    "secondary": "#334155",
    "header": "#0B1220",
    "selection": "#1D4ED8",
    "scroll": "#475569",
}

LIGHT_PALETTE = {
    "window": "#F4F7FB",
    "surface": "#FFFFFF",
    "surface_alt": "#E9EEF5",
    "surface_hover": "#EEF4FF",
    "border": "#B8C4D4",
    "border_soft": "#D7DEE8",
    "text": "#172033",
    "text_strong": "#0F172A",
    "text_muted": "#526173",
    "primary": "#1D4ED8",
    "primary_hover": "#1E40AF",
    "focus": "#0284C7",
    "danger": "#DC2626",
    "secondary": "#64748B",
    "header": "#E2E8F0",
    "selection": "#2563EB",
    "scroll": "#94A3B8",
}


def build_stylesheet(
    theme: str = "dark",
    *,
    font_size: int = 13,
    scale_percent: int = 100,
) -> str:
    palette = LIGHT_PALETTE if theme == "light" else DARK_PALETTE
    scale = max(90, min(140, int(scale_percent))) / 100
    font = max(11, min(20, int(font_size)))
    padding = max(6, round(8 * scale))
    button_v = max(7, round(9 * scale))
    button_h = max(11, round(14 * scale))
    radius = max(6, round(8 * scale))
    row_height = max(28, round(34 * scale))
    tab_v = max(8, round(10 * scale))
    tab_h = max(13, round(18 * scale))
    scroll_size = max(12, round(14 * scale))

    return f"""
QWidget {{
    font-family: "Segoe UI", "Tahoma", "Arial";
    font-size: {font}px;
    color: {palette["text"]};
    background-color: {palette["window"]};
}}

QDialog, QMainWindow {{
    background-color: {palette["window"]};
}}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox,
QDoubleSpinBox, QDateEdit, QDateTimeEdit, QTimeEdit {{
    min-height: {row_height}px;
    background-color: {palette["surface"]};
    border: 1px solid {palette["border"]};
    border-radius: {radius}px;
    padding: {padding}px;
    color: {palette["text_strong"]};
    selection-background-color: {palette["selection"]};
    selection-color: #FFFFFF;
}}

QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus,
QDateTimeEdit:focus, QTimeEdit:focus {{
    border: 2px solid {palette["focus"]};
}}

QComboBox QAbstractItemView {{
    background-color: {palette["surface"]};
    color: {palette["text_strong"]};
    border: 1px solid {palette["border"]};
    selection-background-color: {palette["selection"]};
    selection-color: #FFFFFF;
    outline: 0;
}}

QPushButton, QToolButton {{
    min-height: {row_height}px;
    background-color: {palette["primary"]};
    border: none;
    border-radius: {radius}px;
    padding: {button_v}px {button_h}px;
    color: #FFFFFF;
    font-weight: 600;
}}

QPushButton:hover, QToolButton:hover {{
    background-color: {palette["primary_hover"]};
}}

QPushButton:disabled, QToolButton:disabled {{
    background-color: {palette["border"]};
    color: {palette["text_muted"]};
}}

QPushButton#secondaryButton, QToolButton#secondaryButton {{
    background-color: {palette["secondary"]};
}}

QPushButton#dangerButton {{
    background-color: {palette["danger"]};
}}

QLabel#titleLabel {{
    font-size: {round(font * 1.75)}px;
    font-weight: 800;
    color: {palette["text_strong"]};
}}

QLabel#subtitleLabel {{
    color: {palette["text_muted"]};
}}

QLabel#appHeader {{
    font-size: {round(font * 1.15)}px;
    font-weight: 800;
    color: {palette["text_strong"]};
    padding: 4px;
}}

QFrame#card, QGroupBox {{
    background-color: {palette["surface"]};
    border: 1px solid {palette["border_soft"]};
    border-radius: {max(10, round(14 * scale))}px;
    margin-top: 10px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top right;
    padding: 0 8px;
    color: {palette["text_strong"]};
    font-weight: 700;
}}

QListWidget {{
    background-color: {palette["surface_alt"]};
    color: {palette["text"]};
    border: none;
    outline: none;
}}

QListWidget::item {{
    min-height: {row_height}px;
    padding: {max(9, round(13 * scale))}px {max(12, round(16 * scale))}px;
    border-radius: {radius}px;
    margin: 4px 8px;
}}

QListWidget::item:hover {{
    background-color: {palette["surface_hover"]};
}}

QListWidget::item:selected {{
    background-color: {palette["selection"]};
    color: #FFFFFF;
}}

QTabWidget::pane {{
    background-color: {palette["surface"]};
    border: 1px solid {palette["border"]};
    border-radius: {radius}px;
    top: -1px;
}}

QTabBar::tab {{
    background-color: {palette["surface_alt"]};
    color: {palette["text_strong"]};
    border: 1px solid {palette["border"]};
    padding: {tab_v}px {tab_h}px;
    min-width: {round(105 * scale)}px;
    font-weight: 700;
}}

QTabBar::tab:selected {{
    background-color: {palette["primary"]};
    color: #FFFFFF;
    border-color: {palette["primary"]};
}}

QTabBar::tab:hover:!selected {{
    background-color: {palette["surface_hover"]};
    color: {palette["text_strong"]};
}}

QTableWidget, QTableView, QTreeWidget {{
    background-color: {palette["surface"]};
    alternate-background-color: {palette["surface_alt"]};
    color: {palette["text_strong"]};
    border: 1px solid {palette["border"]};
    border-radius: {radius}px;
    gridline-color: {palette["border_soft"]};
    selection-background-color: {palette["selection"]};
    selection-color: #FFFFFF;
}}

QHeaderView::section {{
    min-height: {row_height}px;
    background-color: {palette["header"]};
    color: {palette["text_strong"]};
    border: none;
    border-left: 1px solid {palette["border"]};
    border-bottom: 1px solid {palette["border"]};
    padding: {padding}px;
    font-weight: 700;
}}

QTableCornerButton::section {{
    background-color: {palette["header"]};
    border: 1px solid {palette["border"]};
}}

QMenu {{
    background-color: {palette["surface"]};
    color: {palette["text_strong"]};
    border: 1px solid {palette["border"]};
    border-radius: {radius}px;
    padding: 6px;
}}

QMenu::item {{
    min-height: {row_height}px;
    padding: 8px 14px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {palette["selection"]};
    color: #FFFFFF;
}}

QToolTip {{
    background-color: {palette["surface"]};
    color: {palette["text_strong"]};
    border: 1px solid {palette["border"]};
    padding: 6px;
}}

QScrollArea#contentScrollArea {{
    border: none;
    background-color: {palette["window"]};
}}

QScrollBar:vertical {{
    background: {palette["header"]};
    width: {scroll_size}px;
    margin: 2px;
    border-radius: {scroll_size // 2}px;
}}

QScrollBar::handle:vertical {{
    background: {palette["scroll"]};
    min-height: 30px;
    border-radius: {max(5, scroll_size // 2 - 1)}px;
}}

QScrollBar::handle:vertical:hover {{
    background: {palette["primary"]};
}}

QScrollBar:horizontal {{
    background: {palette["header"]};
    height: {scroll_size}px;
    margin: 2px;
    border-radius: {scroll_size // 2}px;
}}

QScrollBar::handle:horizontal {{
    background: {palette["scroll"]};
    min-width: 30px;
    border-radius: {max(5, scroll_size // 2 - 1)}px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {palette["primary"]};
}}

QScrollBar::add-line, QScrollBar::sub-line {{
    width: 0;
    height: 0;
    background: transparent;
}}

QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}
"""


APP_STYLESHEET = build_stylesheet("dark", font_size=13, scale_percent=100)


__all__ = ["APP_STYLESHEET", "build_stylesheet"]
