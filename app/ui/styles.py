APP_STYLESHEET = """
QWidget {
    font-family: "Segoe UI", "Tahoma", "Arial";
    font-size: 13px;
    color: #E5E7EB;
    background-color: #0F172A;
}

QDialog, QMainWindow {
    background-color: #0F172A;
}

QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QTableWidget {
    background-color: #111827;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 8px;
    color: #F8FAFC;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #38BDF8;
}

QPushButton {
    background-color: #2563EB;
    border: none;
    border-radius: 8px;
    padding: 9px 14px;
    color: white;
    font-weight: 600;
}

QPushButton:hover {
    background-color: #1D4ED8;
}

QPushButton#secondaryButton {
    background-color: #334155;
}

QPushButton#dangerButton {
    background-color: #DC2626;
}

QLabel#titleLabel {
    font-size: 24px;
    font-weight: 800;
    color: #F8FAFC;
}

QLabel#subtitleLabel {
    font-size: 13px;
    color: #94A3B8;
}

QFrame#card {
    background-color: #111827;
    border: 1px solid #1F2937;
    border-radius: 14px;
}

QListWidget {
    background-color: #020617;
    border: none;
    outline: none;
}

QListWidget::item {
    padding: 13px 16px;
    border-radius: 8px;
    margin: 4px 8px;
}

QListWidget::item:selected {
    background-color: #1D4ED8;
    color: #FFFFFF;
}

QScrollArea#contentScrollArea {
    border: none;
    background-color: #0F172A;
}

QScrollBar:vertical {
    background: #0B1220;
    width: 14px;
    margin: 2px;
    border-radius: 7px;
}

QScrollBar::handle:vertical {
    background: #475569;
    min-height: 30px;
    border-radius: 6px;
}

QScrollBar::handle:vertical:hover {
    background: #3B82F6;
}

QScrollBar:horizontal {
    background: #0B1220;
    height: 14px;
    margin: 2px;
    border-radius: 7px;
}

QScrollBar::handle:horizontal {
    background: #475569;
    min-width: 30px;
    border-radius: 6px;
}

QScrollBar::handle:horizontal:hover {
    background: #3B82F6;
}

QScrollBar::add-line,
QScrollBar::sub-line {
    width: 0;
    height: 0;
    background: transparent;
}

QScrollBar::add-page,
QScrollBar::sub-page {
    background: transparent;
}
"""
