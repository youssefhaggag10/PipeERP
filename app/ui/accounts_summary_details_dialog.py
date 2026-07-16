from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class AccountsSummaryDetailsDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        total: float,
        headers: list[str],
        rows: list[list[object]],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1050, 620)

        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")
        total_label = QLabel(f"إجمالي الكارت: {float(total):,.2f}")
        total_label.setStyleSheet(
            "font-size: 22px; font-weight: 900; color: #38BDF8; padding: 8px;"
        )

        table = QTableWidget(len(rows), len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setAlternatingRowColors(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setStretchLastSection(True)

        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                item.setToolTip(str(value))
                table.setItem(row_index, column_index, item)

        empty_label = QLabel("لا توجد تفاصيل مسجلة لهذا الرقم")
        empty_label.setAlignment(Qt.AlignCenter)
        empty_label.setObjectName("subtitleLabel")
        empty_label.setVisible(not rows)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title_label)
        layout.addWidget(total_label)
        layout.addWidget(empty_label)
        layout.addWidget(table, 1)
        layout.addWidget(buttons)


__all__ = ["AccountsSummaryDetailsDialog"]
