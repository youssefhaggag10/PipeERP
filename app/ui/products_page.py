from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.repositories.product_repository import ProductRepository

PRODUCT_TYPES = {
    "خامة": "raw_material",
    "منتج نهائي": "finished_good",
    "هالك": "waste",
    "خدمة": "service",
    "قطعة غيار": "spare_part",
}
PRODUCT_TYPE_LABELS = {value: key for key, value in PRODUCT_TYPES.items()}


class ProductsPage(QWidget):
    def __init__(self, repository: ProductRepository) -> None:
        super().__init__()
        self.repository = repository
        self.products = []
        self.editing_product_id: int | None = None
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الأصناف")
        title.setObjectName("titleLabel")

        self.code_input = QLineEdit()
        self.name_input = QLineEdit()
        self.unit_input = QLineEdit("كجم")
        self.min_stock_input = QLineEdit("0")
        self.standard_weight_input = QLineEdit("0")
        self.standard_weight_input.setToolTip(
            "وزن القطعة القياسي للمنتج النهائي؛ يستخدم لحساب خلطات التصنيع"
        )
        self.type_input = QComboBox()
        self.type_input.addItems(PRODUCT_TYPES.keys())

        form = QFormLayout()
        form.addRow("الكود", self.code_input)
        form.addRow("الاسم", self.name_input)
        form.addRow("النوع", self.type_input)
        form.addRow("الوحدة", self.unit_input)
        form.addRow("حد التنبيه", self.min_stock_input)
        form.addRow("وزن القطعة القياسي (كجم)", self.standard_weight_input)

        self.save_button = QPushButton("حفظ الصنف")
        self.save_button.clicked.connect(self.save_product)
        cancel_edit_button = QPushButton("إلغاء التعديل")
        cancel_edit_button.setObjectName("secondaryButton")
        cancel_edit_button.clicked.connect(self.clear_editor)
        delete_button = QPushButton("حذف الصنف المحدد")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_selected_product)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["الكود", "الاسم", "النوع", "الوحدة", "الوزن القياسي كجم", "حد التنبيه"]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.doubleClicked.connect(self.load_selected_product)

        actions = QHBoxLayout()
        actions.addWidget(self.save_button)
        actions.addWidget(cancel_edit_button)
        actions.addWidget(delete_button)
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
            "standard_weight_kg": self.standard_weight_input.text().strip() or "0",
            "track_lots": True,
        }
        if not data["code"] or not data["name"]:
            QMessageBox.warning(self, "تنبيه", "الكود والاسم مطلوبان")
            return
        try:
            standard_weight = float(data["standard_weight_kg"])
            if standard_weight < 0:
                raise ValueError
            if self.editing_product_id is None:
                self.repository.create_product(data)
            else:
                self.repository.update_product(self.editing_product_id, data)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الوزن القياسي يجب أن يكون رقمًا غير سالب")
            return
        self.clear_editor()
        self.reload()

    def load_selected_product(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.products):
            return
        product = self.products[row]
        self.editing_product_id = int(product["id"])
        self.code_input.setText(str(product["code"]))
        self.name_input.setText(str(product["name"]))
        type_label = PRODUCT_TYPE_LABELS.get(product["product_type"])
        if type_label:
            self.type_input.setCurrentText(type_label)
        self.unit_input.setText(str(product["unit"]))
        self.min_stock_input.setText(f"{float(product['min_stock']):g}")
        self.standard_weight_input.setText(f"{float(product.get('standard_weight_kg', 0)):g}")
        self.save_button.setText("حفظ تعديلات الصنف")

    def clear_editor(self) -> None:
        self.editing_product_id = None
        self.code_input.clear()
        self.name_input.clear()
        self.unit_input.setText("كجم")
        self.min_stock_input.setText("0")
        self.standard_weight_input.setText("0")
        self.save_button.setText("حفظ الصنف")

    def delete_selected_product(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.products):
            QMessageBox.warning(self, "تنبيه", "اختار صنف من الجدول أولًا")
            return
        product = self.products[row]
        confirm = QMessageBox.question(
            self, "تأكيد الحذف", f"هل تريد حذف الصنف: {product['name']}؟"
        )
        if confirm != QMessageBox.Yes:
            return
        self.repository.delete_product(int(product["id"]))
        self.reload()

    def reload(self) -> None:
        self.products = self.repository.list_products()
        self.table.setRowCount(len(self.products))
        for row_index, product in enumerate(self.products):
            values = [
                product["code"],
                product["name"],
                PRODUCT_TYPE_LABELS.get(product["product_type"], product["product_type"]),
                product["unit"],
                f"{float(product.get('standard_weight_kg', 0)):g}",
                str(product["min_stock"]),
            ]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))
