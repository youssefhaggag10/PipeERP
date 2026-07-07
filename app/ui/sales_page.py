from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from app.repositories.partner_repository import PartnerRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.sales_repository import SalesRepository


class SalesPage(QWidget):
    def __init__(self, sales_repository: SalesRepository, partner_repository: PartnerRepository, product_repository: ProductRepository) -> None:
        super().__init__()
        self.sales_repository = sales_repository
        self.partner_repository = partner_repository
        self.product_repository = product_repository
        self.orders = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المبيعات")
        title.setObjectName("titleLabel")
        self.customer_input = QComboBox()
        self.product_input = QComboBox()
        self.qty_input = QLineEdit()
        self.unit_input = QLineEdit("قطعة")
        self.price_input = QLineEdit("0")

        form = QFormLayout()
        form.addRow("العميل", self.customer_input)
        form.addRow("المنتج", self.product_input)
        form.addRow("الكمية", self.qty_input)
        form.addRow("الوحدة", self.unit_input)
        form.addRow("سعر الوحدة", self.price_input)

        create_button = QPushButton("حفظ كمسودة")
        create_button.clicked.connect(self.create_order)
        deliver_button = QPushButton("تسليم المحدد")
        deliver_button.clicked.connect(self.deliver_selected)

        actions = QHBoxLayout()
        actions.addWidget(create_button)
        actions.addWidget(deliver_button)
        actions.addStretch()

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["رقم الأمر", "العميل", "التاريخ", "الحالة", "الإجمالي"])
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
        customers = self.partner_repository.list_partners("customer")
        products = [item for item in self.product_repository.list_products() if item["product_type"] == "finished_good"]
        self.customer_input.clear()
        self.product_input.clear()
        for customer in customers:
            self.customer_input.addItem(customer["name"], customer["id"])
        for product in products:
            self.product_input.addItem(product["code"] + " - " + product["name"], product["id"])
        self.orders = self.sales_repository.list_orders()
        self.table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            values = [order["order_number"], order["customer_name"], order["order_date"], order["status"], order["total"]]
            for col_index, value in enumerate(values):
                self.table.setItem(row_index, col_index, QTableWidgetItem(str(value)))

    def create_order(self) -> None:
        if self.customer_input.currentData() is None or self.product_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "أضف عميل ومنتج نهائي الأول")
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
        self.sales_repository.create_order(int(self.customer_input.currentData()), int(self.product_input.currentData()), quantity, self.unit_input.text().strip() or "قطعة", unit_price)
        self.qty_input.clear()
        self.price_input.setText("0")
        self.reload()

    def deliver_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختار أمر بيع")
            return
        self.sales_repository.deliver_order(int(self.orders[row]["id"]))
        self.reload()
        QMessageBox.information(self, "تم", "تم التسليم وتحديث المخزون")
