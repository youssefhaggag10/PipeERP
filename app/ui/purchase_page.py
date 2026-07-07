from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.partner_repository import PartnerRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.purchase_repository import PurchaseRepository


class PurchasePage(QWidget):
    def __init__(self, purchase_repository: PurchaseRepository, partner_repository: PartnerRepository, product_repository: ProductRepository) -> None:
        super().__init__()
        self.purchase_repository = purchase_repository
        self.partner_repository = partner_repository
        self.product_repository = product_repository
        self.orders: list[dict] = []
        self.suppliers: list[dict] = []
        self.products: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المشتريات")
        title.setObjectName("titleLabel")

        self.supplier_input = QComboBox()
        self.product_input = QComboBox()
        self.lot_input = QLineEdit()
        self.qty_input = QLineEdit()
        self.unit_input = QLineEdit("كجم")
        self.price_input = QLineEdit("0")

        form = QFormLayout()
        form.addRow("المورد", self.supplier_input)
        form.addRow("الصنف", self.product_input)
        form.addRow("LOT / Batch", self.lot_input)
        form.addRow("الكمية", self.qty_input)
        form.addRow("الوحدة", self.unit_input)
        form.addRow("سعر الوحدة", self.price_input)

        create_button = QPushButton("حفظ أمر شراء Draft")
        create_button.clicked.connect(self.create_order)
        receive_button = QPushButton("استلام أمر الشراء المحدد")
        receive_button.clicked.connect(self.receive_selected)

        actions = QHBoxLayout()
        actions.addWidget(create_button)
        actions.addWidget(receive_button)
        actions.addStretch()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["رقم الأمر", "المورد", "التاريخ", "الحالة", "الإجمالي"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        self.setLayout(layout)
        self.reload()

    def reload(self) -> None:
        self.suppliers = self.partner_repository.list_partners("supplier")
        self.products = [item for item in self.product_repository.list_products() if item["product_type"] in ("raw_material", "waste", "spare_part")]
        self.supplier_input.clear()
        self.product_input.clear()
        for supplier in self.suppliers:
            self.supplier_input.addItem(supplier["name"], supplier["id"])
        for product in self.products:
            self.product_input.addItem(f"{product['code']} - {product['name']}", product["id"])
        self.orders = self.purchase_repository.list_orders()
        self.table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            values = [order["order_number"], order["supplier_name"], order["order_date"], order["status"], str(order["total"])]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))

    def create_order(self) -> None:
        if self.supplier_input.currentData() is None or self.product_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "لازم تضيف مورد وصنف خامة الأول")
            return
        try:
            quantity = float(self.qty_input.text().strip())
            unit_price = float(self.price_input.text().strip() or 0)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الكمية والسعر لازم يكونوا أرقام")
            return
        if quantity <= 0:
            QMessageBox.warning(self, "تنبيه", "الكمية لازم تكون أكبر من صفر")
            return
        if not self.lot_input.text().strip():
            QMessageBox.warning(self, "تنبيه", "رقم LOT مطلوب")
            return
        self.purchase_repository.create_order(
            int(self.supplier_input.currentData()),
            int(self.product_input.currentData()),
            self.lot_input.text(),
            quantity,
            self.unit_input.text().strip() or "كجم",
            unit_price,
        )
        self.lot_input.clear()
        self.qty_input.clear()
        self.price_input.setText("0")
        self.reload()

    def receive_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختار أمر شراء من الجدول")
            return
        self.purchase_repository.receive_order(int(self.orders[row]["id"]))
        self.reload()
        QMessageBox.information(self, "تم", "تم الاستلام وتحديث المخزون")
