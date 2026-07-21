from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QDateTime, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateTimeEdit,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.repositories.print_settings_repository import PrintSettingsRepository
from app.services.a4_print_service import A4PrintService
from app.services.weight_invoice_calculator import calculate_weight_invoice

STATUS_LABELS = {
    "draft": "مسودة",
    "delivered": "معتمدة",
    "posted": "معتمدة",
    "cancelled": "ملغاة",
}

COL_CODE = 0
COL_NAME = 1
COL_UNIT = 2
COL_QUANTITY = 3
COL_ACTUAL_WEIGHT = 4
COL_PRICE_KG = 5
COL_LINE_TOTAL = 6
COL_NOTES = 7
COL_STANDARD_WEIGHT = 8
COL_THEORETICAL_WEIGHT = 9


class WeightCardSalesPage(QWidget):
    """Independent invoice page for weight/card sales."""

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
        self.print_settings_repository = PrintSettingsRepository(repository.database)
        self.print_service = A4PrintService()
        self.lines: list[dict] = []
        self.sales: list[dict] = []
        self._refreshing_table = False
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("فاتورة مبيعات بالوزن / الكارتة")
        title.setObjectName("titleLabel")
        intro = QLabel(
            "فاتورة مستقلة عن البيع بالقطعة. قيمة الفاتورة تعتمد على الوزن الفعلي "
            "فقط، بينما الوزن القياسي والنظري للمرجعية وتحليل المخزون."
        )
        intro.setWordWrap(True)
        intro.setObjectName("subtitleLabel")

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_invoice_tab(), "فاتورة وزن جديدة")
        self.tabs.addTab(self._build_history_tab(), "فواتير الوزن")

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(intro)
        layout.addWidget(self.tabs, 1)
        self.reload()

    def _build_invoice_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setObjectName("contentScrollArea")
        content = QWidget()
        layout = QVBoxLayout(content)

        numbers_group = QGroupBox("بيانات المستند")
        numbers_layout = QGridLayout(numbers_group)
        self.order_number_input = self._readonly_line()
        self.invoice_number_input = self._readonly_line()
        self.card_number_input = self._readonly_line()
        self.sale_date_input = QDateTimeEdit(QDateTime.currentDateTime())
        self.sale_date_input.setCalendarPopup(True)
        self.sale_date_input.setDisplayFormat("yyyy-MM-dd HH:mm")
        self.customer_input = QComboBox()
        self.warehouse_input = self._readonly_line("المصنع")
        self.vehicle_input = QLineEdit()
        self.vehicle_input.setPlaceholderText("رقم السيارة أو الحمولة — اختياري")
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("ملاحظات عامة على الفاتورة")
        self.notes_input.setMaximumHeight(86)

        fields = (
            ("رقم أمر البيع", self.order_number_input),
            ("رقم الفاتورة", self.invoice_number_input),
            ("رقم كارتة الوزن", self.card_number_input),
            ("تاريخ البيع", self.sale_date_input),
            ("العميل", self.customer_input),
            ("المخزن", self.warehouse_input),
            ("السيارة / الحمولة", self.vehicle_input),
        )
        for index, (label, widget) in enumerate(fields):
            row = index // 2
            column = (index % 2) * 2
            numbers_layout.addWidget(QLabel(label), row, column)
            numbers_layout.addWidget(widget, row, column + 1)
        notes_row = (len(fields) + 1) // 2
        numbers_layout.addWidget(QLabel("ملاحظات"), notes_row, 0)
        numbers_layout.addWidget(self.notes_input, notes_row, 1, 1, 3)
        numbers_layout.setColumnStretch(1, 1)
        numbers_layout.setColumnStretch(3, 1)
        layout.addWidget(numbers_group)

        modes_group = QGroupBox("طريقة الوزن والتسعير")
        modes_layout = QGridLayout(modes_group)
        self.weight_mode_input = QComboBox()
        self.weight_mode_input.addItem("وزن إجمالي للكارتة", "total_card")
        self.weight_mode_input.addItem("وزن منفصل لكل بند", "per_line")
        self.pricing_mode_input = QComboBox()
        self.pricing_mode_input.addItem("سعر كيلو موحد لكل الكارتة", "uniform")
        self.pricing_mode_input.addItem("سعر كيلو مختلف لكل بند", "per_line")
        self.use_vehicle_scale_input = QCheckBox("حساب الوزن من ميزان السيارة")
        self.net_weight_input = self._weight_spinbox()
        self.net_weight_input.setSuffix(" كجم")
        self.net_weight_input.setToolTip("الوزن الصافي الفعلي للكارتة")
        self.uniform_price_input = self._money_spinbox()
        self.uniform_price_input.setSuffix(" جنيه/كجم")

        modes_layout.addWidget(QLabel("طريقة الوزن"), 0, 0)
        modes_layout.addWidget(self.weight_mode_input, 0, 1)
        modes_layout.addWidget(QLabel("طريقة التسعير"), 0, 2)
        modes_layout.addWidget(self.pricing_mode_input, 0, 3)
        modes_layout.addWidget(self.use_vehicle_scale_input, 1, 0, 1, 2)
        modes_layout.addWidget(QLabel("الوزن الصافي الفعلي"), 1, 2)
        modes_layout.addWidget(self.net_weight_input, 1, 3)
        modes_layout.addWidget(QLabel("سعر الكيلو الموحد"), 2, 2)
        modes_layout.addWidget(self.uniform_price_input, 2, 3)
        modes_layout.setColumnStretch(1, 1)
        modes_layout.setColumnStretch(3, 1)

        self.vehicle_scale_panel = QWidget()
        vehicle_layout = QHBoxLayout(self.vehicle_scale_panel)
        vehicle_layout.setContentsMargins(0, 0, 0, 0)
        self.gross_input = self._weight_spinbox()
        self.gross_input.setSuffix(" كجم")
        self.tare_input = self._weight_spinbox()
        self.tare_input.setSuffix(" كجم")
        vehicle_layout.addWidget(QLabel("الوزن القائم"))
        vehicle_layout.addWidget(self.gross_input)
        vehicle_layout.addWidget(QLabel("وزن السيارة الفارغ"))
        vehicle_layout.addWidget(self.tare_input)
        modes_layout.addWidget(self.vehicle_scale_panel, 2, 0, 1, 2)
        layout.addWidget(modes_group)

        add_group = QGroupBox("إضافة بند")
        add_layout = QHBoxLayout(add_group)
        self.product_input = QComboBox()
        self.quantity_input = self._quantity_spinbox()
        add_button = QPushButton("إضافة البند")
        add_button.clicked.connect(self.add_line)
        remove_button = QPushButton("حذف البند المحدد")
        remove_button.setObjectName("dangerButton")
        remove_button.clicked.connect(self.remove_selected_line)
        self.details_toggle = QCheckBox("تفاصيل إضافية")
        self.details_toggle.toggled.connect(self._toggle_additional_columns)
        add_layout.addWidget(QLabel("المنتج"))
        add_layout.addWidget(self.product_input, 3)
        add_layout.addWidget(QLabel("الكمية"))
        add_layout.addWidget(self.quantity_input, 1)
        add_layout.addWidget(add_button)
        add_layout.addWidget(remove_button)
        add_layout.addWidget(self.details_toggle)
        layout.addWidget(add_group)

        self.lines_table = QTableWidget(0, 10)
        self.lines_table.setHorizontalHeaderLabels(
            [
                "الكود",
                "البيان",
                "الوحدة",
                "الكمية",
                "الوزن الفعلي",
                "سعر الكيلو",
                "الإجمالي",
                "ملاحظات البند",
                "الوزن القياسي",
                "الوزن النظري",
            ]
        )
        self.lines_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.lines_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.lines_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.lines_table.horizontalHeader().setSectionResizeMode(
            COL_NAME, QHeaderView.ResizeMode.Stretch
        )
        self.lines_table.horizontalHeader().setSectionResizeMode(
            COL_NOTES, QHeaderView.ResizeMode.Stretch
        )
        self.lines_table.itemChanged.connect(self._line_item_changed)
        layout.addWidget(self.lines_table, 1)

        charges_group = QGroupBox("إجماليات الفاتورة")
        charges_layout = QGridLayout(charges_group)
        self.discount_input = self._money_spinbox()
        self.transport_input = self._money_spinbox()
        self.tax_input = self._money_spinbox()
        self.total_pieces_label = QLabel("0")
        self.total_weight_label = QLabel("0.000 كجم")
        self.subtotal_label = QLabel("0.00 جنيه")
        self.net_total_label = QLabel("0.00 جنيه")
        self.net_total_label.setObjectName("titleLabel")
        charge_fields = (
            ("إجمالي عدد المواسير", self.total_pieces_label),
            ("إجمالي الوزن الفعلي", self.total_weight_label),
            ("إجمالي البنود", self.subtotal_label),
            ("الخصم", self.discount_input),
            ("النقل", self.transport_input),
            ("الضريبة", self.tax_input),
            ("صافي الفاتورة", self.net_total_label),
        )
        for index, (label, widget) in enumerate(charge_fields):
            row = index // 4
            column = (index % 4) * 2
            charges_layout.addWidget(QLabel(label), row, column)
            charges_layout.addWidget(widget, row, column + 1)
        layout.addWidget(charges_group)

        actions = QHBoxLayout()
        self.save_draft_button = QPushButton("حفظ كمسودة")
        self.save_draft_button.clicked.connect(self.save_draft)
        self.approve_button = QPushButton("اعتماد الفاتورة")
        self.approve_button.clicked.connect(self.approve_current)
        self.approve_print_button = QPushButton("اعتماد وطباعة")
        self.approve_print_button.clicked.connect(self.approve_and_print_current)
        clear_button = QPushButton("تفريغ البيانات")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self.clear_form)
        cancel_button = QPushButton("إلغاء")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.cancel_form)
        for button in (
            self.save_draft_button,
            self.approve_button,
            self.approve_print_button,
            clear_button,
            cancel_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        scroll.setWidget(content)
        page_layout.addWidget(scroll)

        self.weight_mode_input.currentIndexChanged.connect(self._mode_changed)
        self.pricing_mode_input.currentIndexChanged.connect(self._mode_changed)
        self.use_vehicle_scale_input.toggled.connect(self._vehicle_scale_changed)
        self.net_weight_input.valueChanged.connect(self.refresh_totals)
        self.uniform_price_input.valueChanged.connect(self.refresh_totals)
        self.gross_input.valueChanged.connect(self._vehicle_weights_changed)
        self.tare_input.valueChanged.connect(self._vehicle_weights_changed)
        self.discount_input.valueChanged.connect(self.refresh_totals)
        self.transport_input.valueChanged.connect(self.refresh_totals)
        self.tax_input.valueChanged.connect(self.refresh_totals)
        self._vehicle_scale_changed(False)
        self._toggle_additional_columns(False)
        return page

    def _build_history_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.sales_table = QTableWidget(0, 13)
        self.sales_table.setHorizontalHeaderLabels(
            [
                "أمر البيع",
                "الفاتورة",
                "الكارتة",
                "العميل",
                "السيارة",
                "عدد المقاسات",
                "عدد المواسير",
                "الوزن الفعلي",
                "الإجمالي",
                "المدفوع",
                "المتبقي",
                "طريقة الوزن",
                "الحالة",
            ]
        )
        self.sales_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sales_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.sales_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.sales_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.sales_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.sales_table, 1)

        actions = QHBoxLayout()
        approve_button = QPushButton("اعتماد الفاتورة المحددة")
        approve_button.clicked.connect(self.approve_selected)
        print_button = QPushButton("معاينة وطباعة")
        print_button.clicked.connect(self.print_selected)
        export_button = QPushButton("تصدير PDF")
        export_button.clicked.connect(self.export_selected_pdf)
        delete_button = QPushButton("حذف المسودة المحددة")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self.delete_selected)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)
        for button in (
            approve_button,
            print_button,
            export_button,
            delete_button,
            refresh_button,
        ):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)
        return page

    @staticmethod
    def _readonly_line(value: str = "") -> QLineEdit:
        field = QLineEdit(value)
        field.setReadOnly(True)
        return field

    @staticmethod
    def _weight_spinbox() -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(0, 999_999_999)
        field.setDecimals(6)
        field.setSingleStep(1)
        field.setGroupSeparatorShown(True)
        return field

    @staticmethod
    def _money_spinbox() -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(0, 999_999_999)
        field.setDecimals(2)
        field.setSingleStep(1)
        field.setGroupSeparatorShown(True)
        return field

    @staticmethod
    def _quantity_spinbox() -> QDoubleSpinBox:
        field = QDoubleSpinBox()
        field.setRange(0.001, 999_999_999)
        field.setDecimals(3)
        field.setValue(1)
        field.setSingleStep(1)
        field.setGroupSeparatorShown(True)
        return field

    def reload(self) -> None:
        self._reload_customers()
        self._reload_products()
        self._reload_document_numbers()
        self._reload_sales()

    def _reload_document_numbers(self) -> None:
        numbers = self.repository.preview_document_numbers()
        self.order_number_input.setText(str(numbers["order_number"]))
        self.invoice_number_input.setText(str(numbers["invoice_number"]))
        self.card_number_input.setText(str(numbers["card_number"]))

    def _reload_customers(self) -> None:
        selected = self.customer_input.currentData()
        self.customer_input.blockSignals(True)
        self.customer_input.clear()
        self.customer_input.addItem("اختر العميل", None)
        for customer in self.partner_repository.list_partners("customer"):
            label = str(customer["name"])
            code = str(customer.get("code") or "").strip()
            self.customer_input.addItem(
                f"{label} — {code}" if code else label,
                int(customer["id"]),
            )
        if selected is not None:
            index = self.customer_input.findData(selected)
            if index >= 0:
                self.customer_input.setCurrentIndex(index)
        self.customer_input.blockSignals(False)

    def _reload_products(self) -> None:
        selected = self.product_input.currentData()
        self.product_input.clear()
        self.product_input.addItem("اختر المنتج أو المقاس", None)
        for product in self.product_repository.list_products():
            if str(product["product_type"]) != "finished_good":
                continue
            standard = float(product.get("standard_weight_kg", 0) or 0)
            self.product_input.addItem(
                f"{product['code']} — {product['name']}",
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
                Qt.ItemDataRole.UserRole + 1,
            )
        if selected is not None:
            index = self.product_input.findData(selected)
            if index >= 0:
                self.product_input.setCurrentIndex(index)

    def add_line(self) -> None:
        product_id = self.product_input.currentData()
        product = self.product_input.currentData(Qt.ItemDataRole.UserRole + 1)
        if product_id is None or not isinstance(product, dict):
            QMessageBox.warning(self, "تنبيه", "اختر المنتج أو المقاس")
            return
        quantity = float(self.quantity_input.value())
        for line in self.lines:
            if int(line["product_id"]) == int(product_id):
                line["quantity"] = float(line["quantity"]) + quantity
                self.refresh_lines_table()
                self.refresh_totals()
                return
        self.lines.append(
            {
                "product_id": int(product_id),
                "code": str(product["code"]),
                "name": str(product["name"]),
                "unit": str(product["unit"]),
                "quantity": quantity,
                "standard_weight_kg": float(product["standard_weight_kg"]),
                "actual_weight_kg": 0.0,
                "price_per_kg": 0.0,
                "notes": "",
            }
        )
        self.refresh_lines_table()
        self.refresh_totals()

    def remove_selected_line(self) -> None:
        row = self.lines_table.currentRow()
        if row < 0 or row >= len(self.lines):
            QMessageBox.warning(self, "تنبيه", "اختر بندًا من جدول الفاتورة")
            return
        self.lines.pop(row)
        self.refresh_lines_table()
        self.refresh_totals()

    def refresh_lines_table(self) -> None:
        self._refreshing_table = True
        try:
            self.lines_table.setRowCount(len(self.lines))
            weight_mode = str(self.weight_mode_input.currentData())
            pricing_mode = str(self.pricing_mode_input.currentData())
            for row_index, line in enumerate(self.lines):
                theoretical = float(line["quantity"]) * float(
                    line["standard_weight_kg"]
                )
                values = [
                    line["code"],
                    line["name"],
                    line["unit"],
                    f"{float(line['quantity']):g}",
                    (
                        f"{float(line.get('actual_weight_kg', 0)):,.6f}"
                        if weight_mode == "per_line"
                        else "يُوزّع تلقائيًا"
                    ),
                    (
                        f"{float(line.get('price_per_kg', 0)):,.2f}"
                        if pricing_mode == "per_line"
                        else f"{float(self.uniform_price_input.value()):,.2f}"
                    ),
                    f"{float(line.get('line_total', 0)):,.2f}",
                    str(line.get("notes") or ""),
                    f"{float(line['standard_weight_kg']):,.3f}",
                    f"{theoretical:,.3f}",
                ]
                editable_columns = {COL_QUANTITY, COL_NOTES}
                if weight_mode == "per_line":
                    editable_columns.add(COL_ACTUAL_WEIGHT)
                if pricing_mode == "per_line":
                    editable_columns.add(COL_PRICE_KG)
                for column, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if column not in editable_columns:
                        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == COL_CODE:
                        item.setData(Qt.ItemDataRole.UserRole, int(line["product_id"]))
                    self.lines_table.setItem(row_index, column, item)
        finally:
            self._refreshing_table = False
        self._toggle_additional_columns(self.details_toggle.isChecked())

    def _line_item_changed(self, item: QTableWidgetItem) -> None:
        if self._refreshing_table:
            return
        row = item.row()
        if row < 0 or row >= len(self.lines):
            return
        line = self.lines[row]
        try:
            if item.column() == COL_QUANTITY:
                value = float(item.text().replace(",", ""))
                if value <= 0:
                    raise ValueError
                line["quantity"] = value
            elif item.column() == COL_ACTUAL_WEIGHT:
                value = float(item.text().replace(",", ""))
                if value < 0:
                    raise ValueError
                line["actual_weight_kg"] = value
            elif item.column() == COL_PRICE_KG:
                value = float(item.text().replace(",", ""))
                if value < 0:
                    raise ValueError
                line["price_per_kg"] = value
            elif item.column() == COL_NOTES:
                line["notes"] = item.text().strip()
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "أدخل قيمة رقمية صحيحة أكبر من صفر")
            self.refresh_lines_table()
            return
        self.refresh_totals()

    def _mode_changed(self) -> None:
        self.refresh_lines_table()
        self.refresh_totals()

    def _vehicle_scale_changed(self, enabled: bool) -> None:
        self.vehicle_scale_panel.setVisible(enabled)
        self.net_weight_input.setReadOnly(enabled)
        if enabled:
            self._vehicle_weights_changed()
        self.refresh_totals()

    def _vehicle_weights_changed(self) -> None:
        if not self.use_vehicle_scale_input.isChecked():
            return
        net = max(0.0, float(self.gross_input.value()) - float(self.tare_input.value()))
        self.net_weight_input.blockSignals(True)
        self.net_weight_input.setValue(net)
        self.net_weight_input.blockSignals(False)
        self.refresh_totals()

    def _toggle_additional_columns(self, visible: bool) -> None:
        for column in (COL_CODE, COL_STANDARD_WEIGHT, COL_THEORETICAL_WEIGHT):
            self.lines_table.setColumnHidden(column, not visible)

    def _calculation_payload(self) -> dict:
        return calculate_weight_invoice(
            lines=[dict(line) for line in self.lines],
            weight_mode=str(self.weight_mode_input.currentData()),
            pricing_mode=str(self.pricing_mode_input.currentData()),
            total_actual_weight_kg=float(self.net_weight_input.value()),
            uniform_price_per_kg=float(self.uniform_price_input.value()),
        )

    def refresh_totals(self) -> None:
        if not self.lines:
            self.total_pieces_label.setText("0")
            self.total_weight_label.setText("0.000 كجم")
            self.subtotal_label.setText("0.00 جنيه")
            self.net_total_label.setText("0.00 جنيه")
            return
        try:
            result = self._calculation_payload()
        except ValueError:
            pieces = sum(float(line["quantity"]) for line in self.lines)
            weight = (
                float(self.net_weight_input.value())
                if str(self.weight_mode_input.currentData()) == "total_card"
                else sum(float(line.get("actual_weight_kg", 0)) for line in self.lines)
            )
            subtotal = 0.0
            self.total_pieces_label.setText(f"{pieces:g}")
            self.total_weight_label.setText(f"{weight:,.3f} كجم")
            self.subtotal_label.setText(f"{subtotal:,.2f} جنيه")
            net = (
                subtotal
                - float(self.discount_input.value())
                + float(self.transport_input.value())
                + float(self.tax_input.value())
            )
            self.net_total_label.setText(f"{max(0, net):,.2f} جنيه")
            return
        for source, calculated in zip(self.lines, result["lines"], strict=True):
            source["allocated_weight_kg"] = float(calculated["allocated_weight_kg"])
            source["line_total"] = float(calculated["line_total"])
            if str(self.weight_mode_input.currentData()) == "total_card":
                source["display_allocated_weight_kg"] = float(
                    calculated["allocated_weight_kg"]
                )
        subtotal = float(result["subtotal"])
        net = (
            subtotal
            - float(self.discount_input.value())
            + float(self.transport_input.value())
            + float(self.tax_input.value())
        )
        self.total_pieces_label.setText(f"{float(result['total_pieces']):g}")
        self.total_weight_label.setText(
            f"{float(result['total_actual_weight_kg']):,.3f} كجم"
        )
        self.subtotal_label.setText(f"{subtotal:,.2f} جنيه")
        self.net_total_label.setText(f"{max(0, net):,.2f} جنيه")
        self._refreshing_table = True
        try:
            for row_index, calculated in enumerate(result["lines"]):
                actual_item = self.lines_table.item(row_index, COL_ACTUAL_WEIGHT)
                price_item = self.lines_table.item(row_index, COL_PRICE_KG)
                total_item = self.lines_table.item(row_index, COL_LINE_TOTAL)
                if actual_item is not None and str(self.weight_mode_input.currentData()) == "total_card":
                    actual_item.setText(f"{float(calculated['allocated_weight_kg']):,.6f}")
                if price_item is not None and str(self.pricing_mode_input.currentData()) == "uniform":
                    price_item.setText(f"{float(calculated['price_per_kg']):,.2f}")
                if total_item is not None:
                    total_item.setText(f"{float(calculated['line_total']):,.2f}")
        finally:
            self._refreshing_table = False

    def _draft_arguments(self) -> dict:
        if self.customer_input.currentData() is None:
            raise ValueError("اختر العميل")
        if not self.lines:
            raise ValueError("أضف بندًا واحدًا على الأقل")
        return {
            "customer_id": int(self.customer_input.currentData()),
            "lines": [dict(line) for line in self.lines],
            "weight_mode": str(self.weight_mode_input.currentData()),
            "pricing_mode": str(self.pricing_mode_input.currentData()),
            "net_weight_kg": float(self.net_weight_input.value()),
            "uniform_price_per_kg": float(self.uniform_price_input.value()),
            "vehicle_number": self.vehicle_input.text(),
            "gross_weight_kg": (
                float(self.gross_input.value())
                if self.use_vehicle_scale_input.isChecked()
                else None
            ),
            "tare_weight_kg": (
                float(self.tare_input.value())
                if self.use_vehicle_scale_input.isChecked()
                else None
            ),
            "use_vehicle_scale": self.use_vehicle_scale_input.isChecked(),
            "discount_amount": float(self.discount_input.value()),
            "transport_amount": float(self.transport_input.value()),
            "tax_amount": float(self.tax_input.value()),
            "sale_date": self.sale_date_input.dateTime().toString("yyyy-MM-dd HH:mm:ss"),
            "notes": self.notes_input.toPlainText(),
        }

    def _create_current_draft(self) -> dict:
        return self.repository.create_weight_sale_draft(**self._draft_arguments())

    def save_draft(self) -> None:
        try:
            result = self._create_current_draft()
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تعذر حفظ المسودة", str(error))
            return
        self.clear_form()
        self.reload()
        self.tabs.setCurrentIndex(1)
        QMessageBox.information(
            self,
            "تم حفظ المسودة",
            f"تم إنشاء أمر {result['order_number']} وكارتة {result['card_number']} كمسودة.",
        )

    def approve_current(self) -> None:
        self._approve_current(print_after=False)

    def approve_and_print_current(self) -> None:
        self._approve_current(print_after=True)

    def _approve_current(self, *, print_after: bool) -> None:
        try:
            draft = self._create_current_draft()
            approved = self.repository.approve_weight_sale(int(draft["order_id"]))
            if print_after:
                self._preview_invoice(int(approved["invoice_id"]))
        except (KeyError, TypeError, ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "تعذر اعتماد الفاتورة", str(error))
            return
        self.clear_form()
        self.reload()
        self.tabs.setCurrentIndex(1)
        QMessageBox.information(
            self,
            "تم اعتماد الفاتورة",
            f"تم اعتماد فاتورة الوزن رقم {approved['invoice_number']}.",
        )

    def clear_form(self) -> None:
        self.lines.clear()
        self.refresh_lines_table()
        self.vehicle_input.clear()
        self.notes_input.clear()
        self.weight_mode_input.setCurrentIndex(0)
        self.pricing_mode_input.setCurrentIndex(0)
        self.use_vehicle_scale_input.setChecked(False)
        self.gross_input.setValue(0)
        self.tare_input.setValue(0)
        self.net_weight_input.setValue(0)
        self.uniform_price_input.setValue(0)
        self.discount_input.setValue(0)
        self.transport_input.setValue(0)
        self.tax_input.setValue(0)
        self.sale_date_input.setDateTime(QDateTime.currentDateTime())
        self._reload_document_numbers()
        self.refresh_totals()

    def cancel_form(self) -> None:
        if not self.lines and not self.vehicle_input.text().strip() and not self.notes_input.toPlainText().strip():
            return
        answer = QMessageBox.question(
            self,
            "إلغاء البيانات",
            "سيتم تفريغ بيانات الفاتورة الحالية دون حفظ. هل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            self.clear_form()

    def _reload_sales(self) -> None:
        self.sales = self.repository.list_weight_sales()
        self.sales_table.setRowCount(len(self.sales))
        for row_index, sale in enumerate(self.sales):
            values = [
                sale["order_number"],
                sale.get("invoice_number", "") or "—",
                sale["card_number"],
                sale["customer_name"],
                sale.get("vehicle_number", "") or "—",
                sale["product_count"],
                f"{float(sale['total_pieces']):g}",
                f"{float(sale['net_weight_kg']):,.3f}",
                f"{float(sale.get('net_amount', sale['total_amount'])):,.2f}",
                f"{float(sale.get('paid', 0)):,.2f}",
                f"{float(sale.get('remaining', 0)):,.2f}",
                (
                    "إجمالي للكارتة"
                    if str(sale.get("weight_mode")) == "total_card"
                    else "لكل بند"
                ),
                STATUS_LABELS.get(str(sale["status"]), str(sale["status"])),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(sale["order_id"]))
                self.sales_table.setItem(row_index, column, item)

    def _selected_sale(self) -> dict | None:
        row = self.sales_table.currentRow()
        if row < 0 or row >= len(self.sales):
            QMessageBox.warning(self, "تنبيه", "اختر فاتورة وزن من الجدول")
            return None
        return self.sales[row]

    def approve_selected(self) -> None:
        sale = self._selected_sale()
        if sale is None:
            return
        if str(sale["status"]) != "draft":
            QMessageBox.information(self, "تنبيه", "الفاتورة المحددة معتمدة بالفعل")
            return
        answer = QMessageBox.question(
            self,
            "اعتماد فاتورة الوزن",
            "سيتم خصم عدد المواسير ووزنها الفعلي وإنشاء مديونية العميل. هل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            approved = self.repository.approve_weight_sale(int(sale["order_id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الاعتماد", str(error))
            return
        self.reload()
        QMessageBox.information(
            self,
            "تم",
            f"تم اعتماد فاتورة الوزن رقم {approved['invoice_number']}.",
        )

    def print_selected(self) -> None:
        sale = self._selected_sale()
        if sale is None:
            return
        invoice_id = int(sale.get("invoice_id", 0) or 0)
        if invoice_id <= 0:
            QMessageBox.warning(self, "تنبيه", "اعتمد الفاتورة قبل الطباعة")
            return
        try:
            self._preview_invoice(invoice_id)
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "تعذر الطباعة", str(error))

    def _preview_invoice(self, invoice_id: int) -> None:
        document = self.repository.get_weight_invoice_print_data(int(invoice_id))
        self.print_service.preview_weight_invoice(
            document,
            self.print_settings_repository.get_settings(),
            self,
        )

    def export_selected_pdf(self) -> None:
        sale = self._selected_sale()
        if sale is None:
            return
        invoice_id = int(sale.get("invoice_id", 0) or 0)
        if invoice_id <= 0:
            QMessageBox.warning(self, "تنبيه", "اعتمد الفاتورة قبل التصدير")
            return
        default_name = f"Weight-Invoice-{sale.get('invoice_number') or invoice_id}.pdf"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "تصدير فاتورة الوزن PDF",
            str(Path.home() / default_name),
            "PDF Files (*.pdf)",
        )
        if not path:
            return
        try:
            document = self.repository.get_weight_invoice_print_data(invoice_id)
            exported = self.print_service.export_weight_invoice_pdf(
                document,
                self.print_settings_repository.get_settings(),
                path,
            )
        except (ValueError, RuntimeError) as error:
            QMessageBox.warning(self, "تعذر التصدير", str(error))
            return
        QMessageBox.information(self, "تم", f"تم تصدير الفاتورة إلى:\n{exported}")

    def delete_selected(self) -> None:
        sale = self._selected_sale()
        if sale is None:
            return
        if str(sale["status"]) != "draft":
            QMessageBox.warning(self, "تعذر الحذف", "لا يمكن حذف فاتورة وزن معتمدة")
            return
        answer = QMessageBox.question(
            self,
            "حذف المسودة",
            "هل تريد حذف مسودة فاتورة الوزن نهائيًا؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.repository.delete_draft_weight_sale(int(sale["order_id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الحذف", str(error))
            return
        self.reload()


__all__ = ["WeightCardSalesPage"]
