from __future__ import annotations

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

from app.repositories.treasury_invoice_repository import TreasuryInvoiceRepository


STATUS_LABELS = {
    "draft": "مسودة",
    "delivered": "تم التسليم",
    "cancelled": "ملغى",
}


class WeightCardSalesPage(QWidget):
    """Independent page for truck-scale sales without opening the normal sales screen."""

    def __init__(
        self,
        repository,
        partner_repository,
        product_repository,
        warehouse_repository,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.repository = repository
        self.partner_repository = partner_repository
        self.product_repository = product_repository
        self.warehouse_repository = warehouse_repository
        self.invoice_repository = TreasuryInvoiceRepository(repository.database)
        self.lines: list[dict] = []
        self.sales: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("بيع بالوزن / الكارتة")
        title.setObjectName("titleLabel")
        intro = QLabel(
            "هذه شاشة مستقلة للبيع بالكارتة. اختر العميل والمقاسات الموجودة على "
            "السيارة، ثم أدخل الوزن الصافي الفعلي وسعر الكيلو. النظام ينشئ مستند "
            "البيع الداخلي تلقائيًا دون المرور بشاشة البيع العادي."
        )
        intro.setWordWrap(True)

        sale_group = QGroupBox("بيانات كارتة الوزن")
        sale_layout = QVBoxLayout(sale_group)

        header_form = QFormLayout()
        self.customer_input = QComboBox()
        self.vehicle_input = QLineEdit()
        self.vehicle_input.setPlaceholderText("رقم السيارة أو المقطورة")
        self.card_number_input = QLineEdit()
        self.card_number_input.setPlaceholderText("اختياري — رقم تلقائي عند تركه فارغًا")
        header_form.addRow("العميل", self.customer_input)
        header_form.addRow("السيارة", self.vehicle_input)
        header_form.addRow("رقم الكارتة", self.card_number_input)
        sale_layout.addLayout(header_form)

        add_line_layout = QHBoxLayout()
        self.product_input = QComboBox()
        self.quantity_input = QLineEdit()
        self.quantity_input.setPlaceholderText("عدد المواسير")
        add_line_button = QPushButton("إضافة المقاس")
        add_line_button.clicked.connect(self.add_line)
        remove_line_button = QPushButton("حذف البند المحدد")
        remove_line_button.setObjectName("dangerButton")
        remove_line_button.clicked.connect(self.remove_selected_line)
        add_line_layout.addWidget(QLabel("المقاس"))
        add_line_layout.addWidget(self.product_input, 2)
        add_line_layout.addWidget(QLabel("العدد"))
        add_line_layout.addWidget(self.quantity_input, 1)
        add_line_layout.addWidget(add_line_button)
        add_line_layout.addWidget(remove_line_button)
        sale_layout.addLayout(add_line_layout)

        self.lines_table = QTableWidget(0, 5)
        self.lines_table.setHorizontalHeaderLabels(
            ["الكود", "الصنف", "عدد المواسير", "الوزن القياسي", "الوزن النظري"]
        )
        self.lines_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SingleSelection)
        self.lines_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.lines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        sale_layout.addWidget(self.lines_table)

        weights_layout = QGridLayout()
        self.gross_input = QLineEdit()
        self.gross_input.setPlaceholderText("اختياري")
        self.tare_input = QLineEdit()
        self.tare_input.setPlaceholderText("اختياري")
        self.net_input = QLineEdit()
        self.net_input.setPlaceholderText("الوزن الصافي الفعلي بالكيلو")
        self.price_input = QLineEdit()
        self.price_input.setPlaceholderText("سعر الكيلو")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("ملاحظات البيع")
        self.total_label = QLabel("قيمة الكارتة: 0.00")
        self.total_label.setStyleSheet("font-size:18px;font-weight:900;")
        self.net_input.textChanged.connect(self.refresh_total)
        self.price_input.textChanged.connect(self.refresh_total)

        weights_layout.addWidget(QLabel("الوزن القائم"), 0, 0)
        weights_layout.addWidget(self.gross_input, 1, 0)
        weights_layout.addWidget(QLabel("وزن الفارغ"), 0, 1)
        weights_layout.addWidget(self.tare_input, 1, 1)
        weights_layout.addWidget(QLabel("الوزن الصافي الفعلي"), 0, 2)
        weights_layout.addWidget(self.net_input, 1, 2)
        weights_layout.addWidget(QLabel("سعر الكيلو"), 0, 3)
        weights_layout.addWidget(self.price_input, 1, 3)
        weights_layout.addWidget(QLabel("ملاحظات"), 2, 0)
        weights_layout.addWidget(self.notes_input, 3, 0, 1, 3)
        weights_layout.addWidget(self.total_label, 3, 3)
        sale_layout.addLayout(weights_layout)

        save_button = QPushButton("حفظ بيع الوزن كمسودة")
        save_button.clicked.connect(self.save_weight_sale)
        clear_button = QPushButton("تفريغ البيانات")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self.clear_form)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(clear_button)
        actions.addStretch()
        sale_layout.addLayout(actions)

        history_group = QGroupBox("مبيعات الوزن المسجلة")
        history_layout = QVBoxLayout(history_group)
        self.sales_table = QTableWidget(0, 10)
        self.sales_table.setHorizontalHeaderLabels(
            [
                "أمر البيع",
                "الكارتة",
                "العميل",
                "السيارة",
                "عدد المقاسات",
                "عدد المواسير",
                "الوزن الصافي",
                "سعر الكيلو",
                "الإجمالي",
                "الحالة",
            ]
        )
        self.sales_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.sales_table.setSelectionMode(QTableWidget.SingleSelection)
        self.sales_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.sales_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sales_table.horizontalHeader().setStretchLastSection(True)
        history_layout.addWidget(self.sales_table)

        deliver_button = QPushButton("تسليم بيع الوزن المحدد")
        deliver_button.clicked.connect(self.deliver_selected)
        delete_button = QPushButton("حذف المسودة المحددة")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_selected)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)
        history_actions = QHBoxLayout()
        history_actions.addWidget(deliver_button)
        history_actions.addWidget(delete_button)
        history_actions.addWidget(refresh_button)
        history_actions.addStretch()
        history_layout.addLayout(history_actions)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(sale_group, 3)
        layout.addWidget(history_group, 2)
        self.reload()

    def reload(self) -> None:
        self._reload_customers()
        self._reload_products()
        self._reload_sales()

    def _reload_customers(self) -> None:
        selected = self.customer_input.currentData()
        self.customer_input.blockSignals(True)
        self.customer_input.clear()
        self.customer_input.addItem("اختر العميل", None)
        for customer in self.partner_repository.list_partners("customer"):
            label = str(customer["name"])
            code = str(customer.get("code") or "").strip()
            if code:
                label = f"{label} — {code}"
            self.customer_input.addItem(label, int(customer["id"]))
        if selected is not None:
            index = self.customer_input.findData(selected)
            if index >= 0:
                self.customer_input.setCurrentIndex(index)
        self.customer_input.blockSignals(False)

    def _reload_products(self) -> None:
        selected = self.product_input.currentData()
        self.product_input.clear()
        self.product_input.addItem("اختر المقاس", None)
        for product in self.product_repository.list_products():
            if str(product["product_type"]) != "finished_good":
                continue
            standard = float(product.get("standard_weight_kg", 0) or 0)
            self.product_input.addItem(
                f"{product['code']} — {product['name']} — قياسي {standard:g} كجم",
                int(product["id"]),
            )
            self.product_input.setItemData(
                self.product_input.count() - 1,
                {
                    "code": str(product["code"]),
                    "name": str(product["name"]),
                    "standard_weight_kg": standard,
                    "unit": str(product.get("unit") or "ماسورة"),
                },
                Qt.UserRole + 1,
            )
        if selected is not None:
            index = self.product_input.findData(selected)
            if index >= 0:
                self.product_input.setCurrentIndex(index)

    def add_line(self) -> None:
        product_id = self.product_input.currentData()
        product = self.product_input.currentData(Qt.UserRole + 1)
        if product_id is None or not isinstance(product, dict):
            QMessageBox.warning(self, "تنبيه", "اختر المقاس")
            return
        try:
            quantity = float(self.quantity_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "عدد المواسير يجب أن يكون رقمًا")
            return
        if quantity <= 0:
            QMessageBox.warning(self, "تنبيه", "عدد المواسير يجب أن يكون أكبر من صفر")
            return
        for line in self.lines:
            if int(line["product_id"]) == int(product_id):
                line["quantity"] = float(line["quantity"]) + quantity
                self.refresh_lines_table()
                self.quantity_input.clear()
                return
        self.lines.append(
            {
                "product_id": int(product_id),
                "code": product["code"],
                "name": product["name"],
                "quantity": quantity,
                "unit": product["unit"],
                "standard_weight_kg": float(product["standard_weight_kg"]),
            }
        )
        self.quantity_input.clear()
        self.refresh_lines_table()

    def remove_selected_line(self) -> None:
        row = self.lines_table.currentRow()
        if row < 0 or row >= len(self.lines):
            QMessageBox.warning(self, "تنبيه", "اختر بندًا من جدول المقاسات")
            return
        self.lines.pop(row)
        self.refresh_lines_table()

    def refresh_lines_table(self) -> None:
        self.lines_table.setRowCount(len(self.lines))
        for row_index, line in enumerate(self.lines):
            theoretical = float(line["quantity"]) * float(line["standard_weight_kg"])
            values = [
                line["code"],
                line["name"],
                f"{float(line['quantity']):g}",
                f"{float(line['standard_weight_kg']):,.3f}",
                f"{theoretical:,.3f}",
            ]
            for column, value in enumerate(values):
                self.lines_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def refresh_total(self) -> None:
        try:
            total = float(self.net_input.text().strip() or 0) * float(
                self.price_input.text().strip() or 0
            )
        except ValueError:
            total = 0
        self.total_label.setText(f"قيمة الكارتة: {total:,.2f}")

    def save_weight_sale(self) -> None:
        if self.customer_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل")
            return
        if not self.lines:
            QMessageBox.warning(self, "تنبيه", "أضف مقاسًا واحدًا على الأقل")
            return
        try:
            net_weight = float(self.net_input.text().strip())
            price_per_kg = float(self.price_input.text().strip())
            gross = (
                float(self.gross_input.text().strip())
                if self.gross_input.text().strip()
                else None
            )
            tare = (
                float(self.tare_input.text().strip())
                if self.tare_input.text().strip()
                else None
            )
            result = self.repository.create_weight_sale(
                customer_id=int(self.customer_input.currentData()),
                lines=self.lines,
                net_weight_kg=net_weight,
                price_per_kg=price_per_kg,
                card_number=self.card_number_input.text(),
                vehicle_number=self.vehicle_input.text(),
                gross_weight_kg=gross,
                tare_weight_kg=tare,
                notes=self.notes_input.text(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تعذر حفظ البيع", str(error))
            return
        self.clear_form()
        self._reload_sales()
        QMessageBox.information(
            self,
            "تم حفظ بيع الوزن",
            f"تم إنشاء الكارتة رقم {result['card_id']} كمسودة مستقلة.",
        )

    def clear_form(self) -> None:
        self.lines.clear()
        self.refresh_lines_table()
        self.vehicle_input.clear()
        self.card_number_input.clear()
        self.gross_input.clear()
        self.tare_input.clear()
        self.net_input.clear()
        self.price_input.clear()
        self.notes_input.clear()
        self.refresh_total()

    def _reload_sales(self) -> None:
        self.sales = self.repository.list_weight_sales()
        self.sales_table.setRowCount(len(self.sales))
        for row_index, sale in enumerate(self.sales):
            values = [
                sale["order_number"],
                sale["card_number"],
                sale["customer_name"],
                sale.get("vehicle_number", "") or "",
                sale["product_count"],
                f"{float(sale['total_pieces']):g}",
                f"{float(sale['net_weight_kg']):,.3f}",
                f"{float(sale['price_per_kg']):,.2f}",
                f"{float(sale['total_amount']):,.2f}",
                STATUS_LABELS.get(str(sale["status"]), str(sale["status"])),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, int(sale["order_id"]))
                self.sales_table.setItem(row_index, column, item)

    def _selected_order_id(self) -> int | None:
        row = self.sales_table.currentRow()
        if row < 0 or row >= len(self.sales):
            QMessageBox.warning(self, "تنبيه", "اختر بيع وزن من الجدول")
            return None
        return int(self.sales[row]["order_id"])

    def deliver_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        answer = QMessageBox.question(
            self,
            "تأكيد التسليم",
            "سيتم خصم عدد المواسير ووزنها الفعلي من المخزون واعتماد الفاتورة. هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repository.deliver_weight_sale(order_id)
            self.invoice_repository._ensure_invoices()
        except ValueError as error:
            QMessageBox.warning(self, "تعذر التسليم", str(error))
            return
        self._reload_sales()
        QMessageBox.information(self, "تم", "تم تسليم بيع الوزن واعتماد الفاتورة")

    def delete_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        answer = QMessageBox.question(
            self,
            "حذف المسودة",
            "هل تريد حذف بيع الوزن المسودة نهائيًا؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repository.delete_draft_weight_sale(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الحذف", str(error))
            return
        self._reload_sales()


__all__ = ["WeightCardSalesPage"]
