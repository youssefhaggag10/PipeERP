from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.product_repository import ProductRepository


PRODUCT_TYPES = {
    "خامة": "raw_material",
    "منتج نهائي": "finished_good",
    "هالك": "waste",
    "خدمة": "service",
    "قطعة غيار": "spare_part",
}


class ProductsPage(QWidget):
    def __init__(self, repository: ProductRepository) -> None:
        super().__init__()
        self.repository = repository
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الأصناف")
        title.setObjectName("titleLabel")

        self.code_input = QLineEdit()
        self.name_input = QLineEdit()
        self.unit_input = QLineEdit("كجم")
        self.min_stock_input = QLineEdit("0")
        self.type_input = QComboBox()
        self.type_input.addItems(PRODUCT_TYPES.keys())

        form = QFormLayout()
        form.addRow("الكود", self.code_input)
        form.addRow("الاسم", self.name_input)
        form.addRow("النوع", self.type_input)
        form.addRow("الوحدة", self.unit_input)
        form.addRow("حد التنبيه", self.min_stock_input)

        save_button = QPushButton("حفظ الصنف")
        save_button.clicked.connect(self.save_product)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["الكود", "الاسم", "النوع", "الوحدة", "حد التنبيه"])

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addStretch()

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def save_product(self) -> None:
        data = {
            "code": self.code_input.text().strip(),
            "name": self.name_input.text().strip(),
            "product_type": PRODUCT_TYPES[self.type_input.currentText()],
            "unit": self.unit_input.text().strip() or "كجم",
            "min_stock": self.min_stock_input.text().strip() or "0",
            "track_lots": True,
        }
        if not data["code"] or not data["name"]:
            return
        self.repository.create_product(data)
        self.code_input.clear()
        self.name_input.clear()
        self.min_stock_input.setText("0")
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
                str(product["min_stock"]),
            ]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(value))
