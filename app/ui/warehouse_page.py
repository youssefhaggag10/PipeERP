from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.warehouse_repository import WarehouseRepository


class WarehousePage(QWidget):
    def __init__(self, repository: WarehouseRepository) -> None:
        super().__init__()
        self.repository = repository
        self.rows = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("إعداد المخزن")
        title.setObjectName("titleLabel")
        subtitle = QLabel("المخزن الحالي هو المصنع. كل حركات الشراء والبيع والتسوية تسجل عليه.")
        subtitle.setObjectName("subtitleLabel")

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["الكود", "الاسم"])

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        self.repository.ensure_defaults()
        self.rows = self.repository.list_warehouses()
        self.table.setRowCount(len(self.rows))
        for row_index, item in enumerate(self.rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(str(item["code"])))
            self.table.setItem(row_index, 1, QTableWidgetItem(str(item["name"])))
