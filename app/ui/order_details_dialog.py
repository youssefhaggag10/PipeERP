from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class OrderDetailsDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        header_fields: list[tuple[str, str]],
        columns: list[str],
        rows: list[list[str]],
        total: float,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(980, 560)
        self.setLayoutDirection(Qt.RightToLeft)

        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")

        header = QFormLayout()
        for label, value in header_fields:
            header.addRow(label, QLabel(value or "-"))

        table = QTableWidget(len(rows), len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QTableWidgetItem(str(value)))

        total_label = QLabel(f"الإجمالي: {total:,.2f}")
        total_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #38BDF8;")

        close_button = QPushButton("إغلاق")
        close_button.clicked.connect(self.accept)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title_label)
        layout.addLayout(header)
        layout.addWidget(table)
        layout.addWidget(total_label)
        layout.addWidget(close_button)
        self.setLayout(layout)
