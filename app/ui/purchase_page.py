from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.repositories.partner_repository import PartnerRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.ui.order_details_dialog import OrderDetailsDialog


class PurchasePage(QWidget):
    def __init__(
        self,
        purchase_repository: PurchaseRepository,
        partner_repository: PartnerRepository,
        product_repository: ProductRepository,
        warehouse_repository: WarehouseRepository,
    ) -> None:
        super().__init__()
        self.purchase_repository = purchase_repository
        self.partner_repository = partner_repository
        self.product_repository = product_repository
        self.warehouse_repository = warehouse_repository
        self.orders: list[dict] = []
        self.products: list[dict] = []
        self.lines: list[dict] = []
        self.editing_line_index: int | None = None
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("المشتريات")
        title.setObjectName("titleLabel")

        self.supplier_input = QComboBox()
        self.warehouse_input = QComboBox()
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("ملاحظات أمر الشراء")

        header_form = QFormLayout()
        header_form.addRow("المورد", self.supplier_input)
        header_form.addRow("المخزن", self.warehouse_input)
        header_form.addRow("ملاحظات", self.notes_input)

        self.product_input = QComboBox()
        self.product_input.currentIndexChanged.connect(self._sync_product_unit)
        self.lot_input = QLineEdit()
        self.lot_input.setPlaceholderText("مثال: HDPE-2026-07-A")
        self.qty_input = QLineEdit()
        self.unit_input = QLineEdit("كجم")
        self.price_input = QLineEdit("0")

        line_editor = QGridLayout()
        line_editor.addWidget(QLabel("الصنف"), 0, 0)
        line_editor.addWidget(self.product_input, 1, 0)
        line_editor.addWidget(QLabel("رقم الدفعة"), 0, 1)
        line_editor.addWidget(self.lot_input, 1, 1)
        line_editor.addWidget(QLabel("الكمية"), 0, 2)
        line_editor.addWidget(self.qty_input, 1, 2)
        line_editor.addWidget(QLabel("الوحدة"), 0, 3)
        line_editor.addWidget(self.unit_input, 1, 3)
        line_editor.addWidget(QLabel("سعر الوحدة"), 0, 4)
        line_editor.addWidget(self.price_input, 1, 4)

        self.add_line_button = QPushButton("إضافة البند")
        self.add_line_button.clicked.connect(self.add_or_update_line)
        delete_line_button = QPushButton("حذف البند المحدد")
        delete_line_button.setObjectName("dangerButton")
        delete_line_button.clicked.connect(self.delete_selected_line)
        clear_line_button = QPushButton("إلغاء التعديل")
        clear_line_button.setObjectName("secondaryButton")
        clear_line_button.clicked.connect(self.clear_line_editor)

        line_actions = QHBoxLayout()
        line_actions.addWidget(self.add_line_button)
        line_actions.addWidget(delete_line_button)
        line_actions.addWidget(clear_line_button)
        line_actions.addStretch()

        self.lines_table = QTableWidget(0, 7)
        self.lines_table.setHorizontalHeaderLabels(
            ["الكود", "الصنف", "رقم الدفعة", "الكمية", "الوحدة", "سعر الوحدة", "الإجمالي"]
        )
        self.lines_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SingleSelection)
        self.lines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lines_table.doubleClicked.connect(self.load_selected_line)

        self.total_label = QLabel("إجمالي الأمر: 0.00")
        self.total_label.setStyleSheet("font-size: 18px; font-weight: 800; color: #38BDF8;")

        lines_box = QGroupBox("بنود أمر الشراء")
        lines_layout = QVBoxLayout()
        lines_layout.addLayout(line_editor)
        lines_layout.addLayout(line_actions)
        lines_layout.addWidget(self.lines_table)
        lines_layout.addWidget(self.total_label)
        lines_box.setLayout(lines_layout)

        save_button = QPushButton("حفظ أمر الشراء كمسودة")
        save_button.clicked.connect(self.create_order)
        receive_button = QPushButton("استلام الأمر المحدد")
        receive_button.clicked.connect(self.receive_selected)
        details_button = QPushButton("عرض تفاصيل الأمر")
        details_button.setObjectName("secondaryButton")
        details_button.clicked.connect(self.view_selected_order)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(receive_button)
        actions.addWidget(details_button)
        actions.addStretch()

        self.orders_table = QTableWidget(0, 8)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر",
                "المورد",
                "الأصناف",
                "عدد البنود",
                "المخزن",
                "التاريخ",
                "الحالة",
                "الإجمالي",
            ]
        )
        self.orders_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.orders_table.setSelectionMode(QTableWidget.SingleSelection)
        self.orders_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.orders_table.doubleClicked.connect(self.view_selected_order)

        layout = QVBoxLayout()
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addLayout(header_form)
        layout.addWidget(lines_box)
        layout.addLayout(actions)
        layout.addWidget(self.orders_table)
        self.setLayout(layout)
        self.reload()

    def status_label(self, status: str) -> str:
        return {"draft": "مسودة", "received": "تم الاستلام"}.get(status, status)

    def reload(self) -> None:
        selected_supplier = self.supplier_input.currentData()
        selected_warehouse = self.warehouse_input.currentData()
        suppliers = self.partner_repository.list_partners("supplier")
        warehouses = self.warehouse_repository.list_warehouses()
        self.products = [
            item
            for item in self.product_repository.list_products()
            if item["product_type"] in ("raw_material", "finished_good", "waste", "spare_part")
        ]

        self.supplier_input.clear()
        self.warehouse_input.clear()
        self.product_input.clear()
        for supplier in suppliers:
            self.supplier_input.addItem(supplier["name"], supplier["id"])
        for warehouse in warehouses:
            self.warehouse_input.addItem(warehouse["name"], warehouse["id"])
        for product in self.products:
            self.product_input.addItem(f"{product['code']} - {product['name']}", product["id"])
        self._restore_combo_value(self.supplier_input, selected_supplier)
        self._restore_combo_value(self.warehouse_input, selected_warehouse)
        self._sync_product_unit()
        self.reload_orders()

    def reload_orders(self) -> None:
        self.orders = self.purchase_repository.list_orders()
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            summary = str(order["product_summary"])
            visible_summary = summary if len(summary) <= 45 else summary[:42] + "..."
            values = [
                order["order_number"],
                order["supplier_name"],
                visible_summary,
                order["line_count"],
                order["warehouse_name"],
                order["order_date"],
                self.status_label(order["status"]),
                f"{float(order['total']):,.2f}",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    item.setToolTip(summary)
                self.orders_table.setItem(row_index, column_index, item)

    def add_or_update_line(self) -> None:
        product_index = self.product_input.currentIndex()
        if product_index < 0 or product_index >= len(self.products):
            QMessageBox.warning(self, "تنبيه", "أضف صنفًا أولًا")
            return
        try:
            quantity = float(self.qty_input.text().strip())
            unit_price = float(self.price_input.text().strip() or 0)
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الكمية والسعر يجب أن يكونا أرقامًا")
            return
        lot_number = self.lot_input.text().strip()
        if quantity <= 0 or unit_price < 0 or not lot_number:
            QMessageBox.warning(
                self,
                "تنبيه",
                "أدخل رقم دفعة، وكمية أكبر من صفر، وسعرًا غير سالب",
            )
            return
        product = self.products[product_index]
        line = {
            "product_id": int(product["id"]),
            "code": product["code"],
            "name": product["name"],
            "lot_number": lot_number,
            "quantity": quantity,
            "unit": self.unit_input.text().strip() or product["unit"],
            "unit_price": unit_price,
            "line_total": quantity * unit_price,
        }
        if self.editing_line_index is None:
            self.lines.append(line)
        else:
            self.lines[self.editing_line_index] = line
        self.refresh_lines_table()
        self.clear_line_editor()

    def load_selected_line(self) -> None:
        row = self.lines_table.currentRow()
        if row < 0 or row >= len(self.lines):
            return
        self.editing_line_index = row
        line = self.lines[row]
        combo_index = self.product_input.findData(line["product_id"])
        self.product_input.setCurrentIndex(combo_index)
        self.lot_input.setText(str(line["lot_number"]))
        self.qty_input.setText(f"{float(line['quantity']):g}")
        self.unit_input.setText(str(line["unit"]))
        self.price_input.setText(f"{float(line['unit_price']):g}")
        self.add_line_button.setText("تحديث البند")

    def delete_selected_line(self) -> None:
        row = self.lines_table.currentRow()
        if row < 0 or row >= len(self.lines):
            QMessageBox.warning(self, "تنبيه", "اختر بندًا من الجدول")
            return
        del self.lines[row]
        self.refresh_lines_table()
        self.clear_line_editor()

    def clear_line_editor(self) -> None:
        self.editing_line_index = None
        self.lot_input.clear()
        self.qty_input.clear()
        self.price_input.setText("0")
        self.add_line_button.setText("إضافة البند")
        self._sync_product_unit()

    def refresh_lines_table(self) -> None:
        self.lines_table.setRowCount(len(self.lines))
        for row_index, line in enumerate(self.lines):
            values = [
                line["code"],
                line["name"],
                line["lot_number"],
                f"{float(line['quantity']):g}",
                line["unit"],
                f"{float(line['unit_price']):,.2f}",
                f"{float(line['line_total']):,.2f}",
            ]
            for column_index, value in enumerate(values):
                self.lines_table.setItem(row_index, column_index, QTableWidgetItem(str(value)))
        total = sum(float(line["line_total"]) for line in self.lines)
        self.total_label.setText(f"إجمالي الأمر: {total:,.2f}")

    def create_order(self) -> None:
        if self.supplier_input.currentData() is None or self.warehouse_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر المورد والمخزن")
            return
        try:
            order_id = self.purchase_repository.create_order_with_lines(
                supplier_id=int(self.supplier_input.currentData()),
                warehouse_id=int(self.warehouse_input.currentData()),
                lines=self.lines,
                notes=self.notes_input.text(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.lines.clear()
        self.notes_input.clear()
        self.refresh_lines_table()
        self.reload_orders()
        QMessageBox.information(self, "تم", f"تم حفظ أمر الشراء رقم {order_id} كمسودة")

    def selected_order_id(self) -> int | None:
        row = self.orders_table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختر أمر شراء من الجدول")
            return None
        return int(self.orders[row]["id"])

    def receive_selected(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        try:
            self.purchase_repository.receive_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload_orders()
        QMessageBox.information(self, "تم", "تم استلام جميع بنود الأمر وتحديث المخزون")

    def view_selected_order(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        order = self.purchase_repository.get_order_details(order_id)
        rows = [
            [
                line["code"],
                line["name"],
                line["lot_number"],
                f"{float(line['quantity']):g}",
                line["unit"],
                f"{float(line['unit_price']):,.2f}",
                f"{float(line['line_total']):,.2f}",
            ]
            for line in order["lines"]
        ]
        dialog = OrderDetailsDialog(
            title=f"تفاصيل أمر الشراء {order['order_number']}",
            header_fields=[
                ("المورد", order["supplier_name"]),
                ("المخزن", order["warehouse_name"]),
                ("التاريخ", order["order_date"]),
                ("الحالة", self.status_label(order["status"])),
                ("الملاحظات", order["notes"] or ""),
            ],
            columns=["الكود", "الصنف", "الدفعة", "الكمية", "الوحدة", "السعر", "الإجمالي"],
            rows=rows,
            total=float(order["total"]),
            parent=self,
        )
        dialog.exec()

    def _sync_product_unit(self) -> None:
        index = self.product_input.currentIndex()
        if 0 <= index < len(self.products):
            self.unit_input.setText(str(self.products[index]["unit"]))

    @staticmethod
    def _restore_combo_value(combo: QComboBox, value) -> None:
        if value is None:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)
