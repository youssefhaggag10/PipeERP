from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class InvoiceReturnDialog(QDialog):
    def __init__(self, lines: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.lines = lines
        self.quantity_inputs: dict[int, QDoubleSpinBox] = {}
        self.setWindowTitle("إنشاء مرتجع فاتورة")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(900, 520)

        note = QLabel(
            "أدخل كمية المرتجع أمام كل صنف. لا يمكن تجاوز الكمية المتبقية القابلة للإرجاع."
        )
        note.setWordWrap(True)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "الكود",
                "الصنف",
                "الكمية الأصلية",
                "مرتجع سابق",
                "المتاح للإرجاع",
                "الوحدة",
                "كمية المرتجع الآن",
            ]
        )
        self.table.setRowCount(len(lines))
        for row_index, line in enumerate(lines):
            values = [
                line["code"],
                line["name"],
                f"{float(line['quantity']):g}",
                f"{float(line['returned_quantity']):g}",
                f"{float(line['remaining_quantity']):g}",
                line["unit"],
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(row_index, column, item)
            quantity_input = QDoubleSpinBox()
            quantity_input.setDecimals(3)
            quantity_input.setMinimum(0)
            quantity_input.setMaximum(float(line["remaining_quantity"]))
            quantity_input.setSingleStep(1)
            quantity_input.setAlignment(Qt.AlignCenter)
            self.table.setCellWidget(row_index, 6, quantity_input)
            self.quantity_inputs[int(line["order_line_id"])] = quantity_input

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("مثال: عيب تصنيع، كمية زائدة، رفض العميل...")
        form = QFormLayout()
        form.addRow("سبب المرتجع", self.reason_input)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("حفظ المرتجع")
        buttons.button(QDialogButtonBox.Cancel).setText("إلغاء")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(self.table)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def quantities(self) -> dict[int, float]:
        return {
            line_id: control.value()
            for line_id, control in self.quantity_inputs.items()
            if control.value() > 0
        }

    def reason(self) -> str:
        return self.reason_input.text().strip()


__all__ = ["InvoiceReturnDialog"]
