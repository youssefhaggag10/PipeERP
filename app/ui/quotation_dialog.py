from __future__ import annotations

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.repositories.print_settings_repository import PrintSettingsRepository
from app.repositories.quotation_repository import QuotationRepository
from app.services.a4_print_service import A4PrintService
from app.utils.datetime_utils import format_egypt_datetime


class QuotationDialog(QDialog):
    def __init__(self, repository: QuotationRepository, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.lines: list[dict] = []
        self.print_service = A4PrintService()
        self.setWindowTitle("عروض الأسعار")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(1100, 760)

        tabs = QTabWidget()
        tabs.addTab(self._build_create_tab(), "إنشاء عرض سعر")
        tabs.addTab(self._build_list_tab(), "العروض المحفوظة")

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        self.reload_reference_data()
        self.reload_quotations()

    def _build_create_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        form = QFormLayout()
        self.customer_input = QComboBox()
        self.product_input = QComboBox()
        self.item_name_input = QLineEdit()
        self.item_name_input.setPlaceholderText("يمكن اختيار صنف أو كتابة بيان يدوي")
        self.unit_input = QLineEdit("وحدة")
        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setRange(0.001, 999999999)
        self.quantity_input.setDecimals(3)
        self.quantity_input.setValue(1)
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0, 999999999)
        self.price_input.setDecimals(2)
        self.line_notes_input = QLineEdit()
        self.valid_until_input = QDateEdit(QDate.currentDate().addDays(15))
        self.valid_until_input.setCalendarPopup(True)
        self.valid_until_input.setDisplayFormat("yyyy-MM-dd")
        self.notes_input = QLineEdit()

        self.product_input.currentIndexChanged.connect(self._product_changed)

        form.addRow("العميل", self.customer_input)
        form.addRow("الصنف من النظام", self.product_input)
        form.addRow("بيان البند", self.item_name_input)
        form.addRow("الوحدة", self.unit_input)
        form.addRow("الكمية", self.quantity_input)
        form.addRow("سعر الوحدة", self.price_input)
        form.addRow("ملاحظات البند", self.line_notes_input)
        form.addRow("العرض صالح حتى", self.valid_until_input)
        form.addRow("ملاحظات عامة", self.notes_input)
        layout.addLayout(form)

        add_button = QPushButton("إضافة البند")
        add_button.clicked.connect(self.add_line)
        layout.addWidget(add_button)

        self.lines_table = QTableWidget(0, 7)
        self.lines_table.setHorizontalHeaderLabels(
            ["م", "البيان", "الكمية", "الوحدة", "سعر الوحدة", "الإجمالي", "ملاحظات"]
        )
        self.lines_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.lines_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.lines_table)

        actions = QHBoxLayout()
        remove_button = QPushButton("حذف البند المحدد")
        remove_button.setObjectName("dangerButton")
        remove_button.clicked.connect(self.remove_selected_line)
        save_button = QPushButton("حفظ عرض السعر")
        save_button.clicked.connect(self.save_quotation)
        actions.addWidget(remove_button)
        actions.addStretch()
        actions.addWidget(save_button)
        layout.addLayout(actions)

        self.total_label = QLabel("الإجمالي: 0.00")
        self.total_label.setObjectName("titleLabel")
        layout.addWidget(self.total_label)
        return page

    def _build_list_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.quotations_table = QTableWidget(0, 8)
        self.quotations_table.setHorizontalHeaderLabels(
            [
                "المعرف",
                "رقم العرض",
                "التاريخ",
                "العميل",
                "الهاتف",
                "عدد البنود",
                "الإجمالي",
                "صالح حتى",
            ]
        )
        self.quotations_table.setColumnHidden(0, True)
        self.quotations_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.quotations_table.setEditTriggers(QTableWidget.NoEditTriggers)
        layout.addWidget(self.quotations_table)

        buttons = QHBoxLayout()
        refresh_button = QPushButton("تحديث")
        refresh_button.clicked.connect(self.reload_quotations)
        preview_button = QPushButton("معاينة وطباعة عرض السعر A4")
        preview_button.clicked.connect(self.preview_selected)
        buttons.addWidget(refresh_button)
        buttons.addStretch()
        buttons.addWidget(preview_button)
        layout.addLayout(buttons)
        return page

    def reload_reference_data(self) -> None:
        self.customer_input.clear()
        self.customer_input.addItem("اختر العميل", None)
        for customer in self.repository.list_customers():
            label = customer["name"]
            if customer["phone"]:
                label += f" — {customer['phone']}"
            self.customer_input.addItem(label, int(customer["id"]))

        self.product_input.clear()
        self.product_input.addItem("بند يدوي", None)
        for product in self.repository.list_products():
            self.product_input.addItem(
                f"{product['code']} — {product['name']}",
                product,
            )

    def _product_changed(self) -> None:
        product = self.product_input.currentData()
        if not isinstance(product, dict):
            return
        self.item_name_input.setText(str(product["name"]))
        self.unit_input.setText(str(product["unit"]))

    def add_line(self) -> None:
        item_name = self.item_name_input.text().strip()
        if not item_name:
            QMessageBox.warning(self, "تنبيه", "اكتب بيان البند أو اختر صنفًا")
            return
        product = self.product_input.currentData()
        line = {
            "product_id": product.get("id") if isinstance(product, dict) else None,
            "item_name": item_name,
            "quantity": float(self.quantity_input.value()),
            "unit": self.unit_input.text().strip() or "وحدة",
            "unit_price": float(self.price_input.value()),
            "notes": self.line_notes_input.text().strip(),
        }
        line["line_total"] = line["quantity"] * line["unit_price"]
        self.lines.append(line)
        self.refresh_lines()
        self.item_name_input.clear()
        self.line_notes_input.clear()
        self.quantity_input.setValue(1)
        self.price_input.setValue(0)
        self.product_input.setCurrentIndex(0)

    def remove_selected_line(self) -> None:
        row = self.lines_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر بندًا من الجدول")
            return
        self.lines.pop(row)
        self.refresh_lines()

    def refresh_lines(self) -> None:
        self.lines_table.setRowCount(len(self.lines))
        total = 0.0
        for row, line in enumerate(self.lines):
            total += float(line["line_total"])
            values = [
                row + 1,
                line["item_name"],
                f"{float(line['quantity']):g}",
                line["unit"],
                f"{float(line['unit_price']):,.2f}",
                f"{float(line['line_total']):,.2f}",
                line["notes"],
            ]
            for column, value in enumerate(values):
                self.lines_table.setItem(row, column, QTableWidgetItem(str(value)))
        self.total_label.setText(f"الإجمالي: {total:,.2f}")

    def save_quotation(self) -> None:
        customer_id = self.customer_input.currentData()
        if customer_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل")
            return
        try:
            quotation_id = self.repository.create_quotation(
                customer_id=int(customer_id),
                lines=self.lines,
                notes=self.notes_input.text(),
                valid_until=self.valid_until_input.date().toString("yyyy-MM-dd"),
            )
        except (TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.lines.clear()
        self.notes_input.clear()
        self.refresh_lines()
        self.reload_quotations()
        QMessageBox.information(self, "تم", f"تم حفظ عرض السعر رقم {quotation_id}")

    def reload_quotations(self) -> None:
        rows = self.repository.list_quotations()
        self.quotations_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["id"],
                row["quotation_number"],
                format_egypt_datetime(row["quotation_date"]),
                row["customer_name"],
                row["customer_phone"],
                row["line_count"],
                f"{float(row['total']):,.2f}",
                row["valid_until"] or "—",
            ]
            for column, value in enumerate(values):
                self.quotations_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(str(value)),
                )

    def preview_selected(self) -> None:
        row = self.quotations_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر عرض سعر من الجدول")
            return
        quotation_id = int(self.quotations_table.item(row, 0).text())
        try:
            data = self.repository.get_print_data(quotation_id)
            settings = PrintSettingsRepository(self.repository.database).get_settings()
            self.print_service.preview_document(data, settings, self)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))


__all__ = ["QuotationDialog"]
