from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

EPSILON = 0.000001


class CustomerPaymentAllocationDialog(QDialog):
    """Allocate one customer receipt to any number of posted invoices."""

    def __init__(self, invoices: list[dict], amount: float, parent=None) -> None:
        super().__init__(parent)
        self.invoices = invoices
        self.amount = float(amount)
        self.inputs: list[QDoubleSpinBox] = []
        self.setWindowTitle("توزيع تحصيل العميل على الفواتير")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(920, 560)

        title = QLabel(f"مبلغ التحصيل: {self.amount:,.2f} جنيه")
        title.setObjectName("titleLabel")
        explanation = QLabel(
            "أدخل المبلغ المخصص لكل فاتورة. أي جزء غير موزع يُحفظ كدفعة عامة "
            "على حساب العميل، ولا يجوز أن يتجاوز مجموع التوزيع مبلغ التحصيل."
        )
        explanation.setWordWrap(True)

        self.table = QTableWidget(len(invoices), 7)
        self.table.setHorizontalHeaderLabels(
            [
                "رقم الفاتورة",
                "رقم الأمر",
                "النوع",
                "تاريخ الفاتورة",
                "صافي الفاتورة",
                "المتبقي",
                "المبلغ المخصص",
            ]
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.horizontalHeader().setStretchLastSection(True)
        for row_index, invoice in enumerate(invoices):
            values = [
                invoice["invoice_number"],
                invoice["order_number"],
                "وزن" if str(invoice["invoice_type"]) == "weight" else "عادي",
                str(invoice["invoice_date"])[:10],
                f"{float(invoice['net_invoice_total']):,.2f}",
                f"{float(invoice['remaining']):,.2f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.ItemDataRole.UserRole, int(invoice["id"]))
                self.table.setItem(row_index, column, item)
            allocation_input = QDoubleSpinBox()
            allocation_input.setRange(0, float(invoice["remaining"]))
            allocation_input.setDecimals(2)
            allocation_input.setSingleStep(1)
            allocation_input.setGroupSeparatorShown(True)
            allocation_input.valueChanged.connect(self._refresh_totals)
            self.inputs.append(allocation_input)
            self.table.setCellWidget(row_index, 6, allocation_input)

        auto_button = QPushButton("توزيع تلقائي على الأقدم")
        auto_button.clicked.connect(self.allocate_oldest_first)
        clear_button = QPushButton("مسح التوزيع")
        clear_button.setObjectName("secondaryButton")
        clear_button.clicked.connect(self.clear_allocations)
        tools = QHBoxLayout()
        tools.addWidget(auto_button)
        tools.addWidget(clear_button)
        tools.addStretch()

        self.allocated_label = QLabel()
        self.general_label = QLabel()
        self.allocated_label.setStyleSheet("font-weight:800;")
        self.general_label.setStyleSheet("font-weight:800;")
        totals = QHBoxLayout()
        totals.addWidget(self.allocated_label)
        totals.addWidget(self.general_label)
        totals.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("اعتماد التوزيع")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("رجوع")
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(self.table, 1)
        layout.addLayout(tools)
        layout.addLayout(totals)
        layout.addWidget(buttons)
        self._refresh_totals()

    def allocated_amount(self) -> float:
        return sum(float(field.value()) for field in self.inputs)

    def general_amount(self) -> float:
        return max(0.0, self.amount - self.allocated_amount())

    def allocations(self) -> list[dict]:
        result: list[dict] = []
        for invoice, field in zip(self.invoices, self.inputs, strict=True):
            value = float(field.value())
            if value > EPSILON:
                result.append(
                    {
                        "sales_invoice_id": int(invoice["id"]),
                        "amount": value,
                    }
                )
        return result

    def allocate_oldest_first(self) -> None:
        remaining = self.amount
        for invoice, field in zip(self.invoices, self.inputs, strict=True):
            value = min(remaining, float(invoice["remaining"]))
            field.setValue(max(0.0, value))
            remaining -= value
            if remaining <= EPSILON:
                remaining = 0.0

    def clear_allocations(self) -> None:
        for field in self.inputs:
            field.setValue(0)

    def _refresh_totals(self) -> None:
        allocated = self.allocated_amount()
        general = self.amount - allocated
        self.allocated_label.setText(f"الموزع على الفواتير: {allocated:,.2f}")
        self.general_label.setText(f"دفعة عامة غير موزعة: {max(0, general):,.2f}")
        self.general_label.setStyleSheet(
            "font-weight:800;color:#DC2626;" if general < -EPSILON else "font-weight:800;"
        )

    def _validate_and_accept(self) -> None:
        allocated = self.allocated_amount()
        if allocated - self.amount > EPSILON:
            QMessageBox.warning(
                self,
                "تنبيه",
                "إجمالي المبالغ المخصصة أكبر من مبلغ التحصيل.",
            )
            return
        self.accept()


__all__ = ["CustomerPaymentAllocationDialog"]
