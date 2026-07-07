from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.inventory_repository import InventoryRepository


class InventoryPage(QWidget):
    def __init__(self, repository: InventoryRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المخازن")
        title.setObjectName("titleLabel")
        subtitle = QLabel("الرصيد هنا ناتج من حركات المخزون فقط: شراء، تصنيع، بيع، تسوية")
        subtitle.setObjectName("subtitleLabel")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الكود", "الصنف", "النوع", "الوحدة", "الرصيد الحالي"])

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        rows = self.repository.list_stock_on_hand()
        self.table.setRowCount(len(rows))
        for row_index, item in enumerate(rows):
            values = [
                item["code"],
                item["name"],
                item["product_type"],
                item["unit"],
                str(item["quantity"]),
            ]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))
