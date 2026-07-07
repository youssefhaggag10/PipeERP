from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QVBoxLayout, QWidget


class TransactionsListPage(QWidget):
    def __init__(self, title: str, subtitle: str, columns: list[str]) -> None:
        super().__init__()
        self.setLayoutDirection(Qt.RightToLeft)

        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("subtitleLabel")

        self.table = QTableWidget(0, len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def reload(self) -> None:
        self.table.setRowCount(0)
