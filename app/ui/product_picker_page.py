from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.product_repository import ProductRepository


class ProductPickerPage(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        repository: ProductRepository,
        allowed_types: set[str] | None = None,
    ) -> None:
        super().__init__()
        self.title = title
        self.subtitle = subtitle
        self.repository = repository
        self.allowed_types = allowed_types
        self.setLayoutDirection(Qt.RightToLeft)

        title_label = QLabel(title)
        title_label.setObjectName("titleLabel")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("subtitleLabel")

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["الكود", "الصنف", "النوع", "الوحدة"])

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        products = self.repository.list_products()
        if self.allowed_types is not None:
            products = [item for item in products if item["product_type"] in self.allowed_types]
        self.table.setRowCount(len(products))
        for row_index, product in enumerate(products):
            values = [product["code"], product["name"], product["product_type"], product["unit"]]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))
