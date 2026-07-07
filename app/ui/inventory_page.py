from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.product_repository import ProductRepository


class InventoryPage(QWidget):
    def __init__(self, repository: ProductRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المخازن")
        title.setObjectName("titleLabel")
        subtitle = QLabel("كل الأصناف المسجلة تظهر هنا حتى قبل وجود رصيد")
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
        products = self.repository.list_products()
        self.table.setRowCount(len(products))
        for row_index, product in enumerate(products):
            values = [
                product["code"],
                product["name"],
                product["product_type"],
                product["unit"],
                "0",
            ]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))
