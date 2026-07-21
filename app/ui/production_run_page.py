from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.ui.replanned_manufacturing_page import ReplannedManufacturingPage


class MaterialQuantitiesDialog(QDialog):
    def __init__(
        self,
        materials: list[dict],
        *,
        excluded_product_id: int,
        batch_count: int,
        current: dict[int, float] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("الكميات الفعلية لباقي الخامات")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(620, 420)
        self.inputs: dict[int, QLineEdit] = {}
        current = current or {}

        intro = QLabel(
            "أدخل إجمالي الكمية الفعلية المستخدمة في مجموعة الخلطات المعدلة. "
            "الخامة المستبعدة لا تظهر هنا. اترك القيم الافتراضية كما هي إذا لم تتغير."
        )
        intro.setWordWrap(True)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["الخامة", "الكمية القياسية للمجموعة", "الكمية الفعلية"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionMode(QTableWidget.NoSelection)

        visible = [
            row for row in materials if int(row["product_id"]) != int(excluded_product_id)
        ]
        table.setRowCount(len(visible))
        for row_index, material in enumerate(visible):
            product_id = int(material["product_id"])
            default_quantity = float(material["quantity_per_batch"]) * int(batch_count)
            actual_quantity = float(current.get(product_id, default_quantity))
            table.setItem(
                row_index,
                0,
                QTableWidgetItem(f"{material['code']} — {material['name']}"),
            )
            table.setItem(row_index, 1, QTableWidgetItem(f"{default_quantity:,.3f}"))
            field = QLineEdit(f"{actual_quantity:g}")
            self.inputs[product_id] = field
            table.setCellWidget(row_index, 2, field)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("حفظ الكميات")
        buttons.button(QDialogButtonBox.Cancel).setText("رجوع")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(table)
        layout.addWidget(buttons)

    def values(self) -> dict[int, float]:
        result: dict[int, float] = {}
        try:
            for product_id, field in self.inputs.items():
                value = float(field.text().strip() or 0)
                if value < 0:
                    raise ValueError
                result[product_id] = value
        except ValueError as error:
            raise ValueError("كميات الخامات الفعلية يجب أن تكون أرقامًا غير سالبة") from error
        return result


class ProductionCompletionDialog(QDialog):
    def __init__(self, order: dict, parent=None) -> None:
        super().__init__(parent)
        self.order = order
        self.materials = list(order["materials"])
        self.adjustment_quantities: dict[int, dict[int, float]] = {}
        self.output_inputs: dict[int, tuple[QLineEdit, QLineEdit, QLineEdit]] = {}
        self.setWindowTitle(f"تسجيل الناتج وإتمام الأمر — {order['order_number']}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(980, 760)

        root_widget = QWidget()
        root_layout = QVBoxLayout(root_widget)

        intro = QLabel(
            "سجل نتيجة أمر التصنيع مرة واحدة. لا تنشئ سجلًا لكل خلطة. "
            "الخامات صُرفت عند بدء الأمر، وسيحسب النظام الاستخدام والتكلفة الفعلية "
            "ويرد أي كمية لم تُستخدم إلى المخزون."
        )
        intro.setWordWrap(True)
        root_layout.addWidget(intro)

        form = QFormLayout()
        self.planned_batches_input = QLineEdit(str(int(order["planned_batches"])))
        self.planned_batches_input.setReadOnly(True)
        self.actual_batches_input = QLineEdit(str(int(order["actual_batches"])))
        self.full_batches_input = QLineEdit(str(int(order["actual_batches"])))
        self.modified_batches_input = QLineEdit("0")
        form.addRow("عدد الخلطات المخطط", self.planned_batches_input)
        form.addRow("عدد الخلطات الفعلي", self.actual_batches_input)
        form.addRow("الخلطات الكاملة بكل الخامات", self.full_batches_input)
        form.addRow("الخلطات المعدلة", self.modified_batches_input)
        root_layout.addLayout(form)

        root_layout.addWidget(QLabel("الإنتاج الفعلي"))
        self.outputs_table = QTableWidget(len(order["outputs"]), 4)
        self.outputs_table.setHorizontalHeaderLabels(
            ["الصنف", "الإنتاج السليم", "الإنتاج المعيب", "الوزن الفعلي للإنتاج السليم"]
        )
        self.outputs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.outputs_table.setSelectionMode(QTableWidget.NoSelection)
        for row_index, output in enumerate(order["outputs"]):
            self.outputs_table.setItem(
                row_index,
                0,
                QTableWidgetItem(
                    f"{output['code']} — {output['name']} — قياسي "
                    f"{float(output['standard_weight_kg']):g} كجم"
                ),
            )
            good = QLineEdit(f"{float(output['planned_quantity']):g}")
            defective = QLineEdit("0")
            actual_weight = QLineEdit(
                f"{float(output['planned_quantity']) * float(output['standard_weight_kg']):g}"
            )
            self.outputs_table.setCellWidget(row_index, 1, good)
            self.outputs_table.setCellWidget(row_index, 2, defective)
            self.outputs_table.setCellWidget(row_index, 3, actual_weight)
            self.output_inputs[int(output["product_id"])] = (
                good,
                defective,
                actual_weight,
            )
        root_layout.addWidget(self.outputs_table)

        bottom_form = QFormLayout()
        self.scrap_input = QLineEdit("0")
        self.scrap_input.setPlaceholderText("الهالك/الكسر بالكيلو")
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("ملاحظات التشغيل")
        self.notes_input.setMaximumHeight(90)
        bottom_form.addRow("الهالك", self.scrap_input)
        bottom_form.addRow("ملاحظات التشغيل", self.notes_input)
        root_layout.addLayout(bottom_form)

        root_layout.addWidget(QLabel("تعديلات الخلطات"))
        self.adjustments_table = QTableWidget(0, 4)
        self.adjustments_table.setHorizontalHeaderLabels(
            [
                "الخامة التي لم تستخدم",
                "عدد الخلطات بدونها",
                "سبب الاستبعاد",
                "الكميات الفعلية لباقي الخامات",
            ]
        )
        self.adjustments_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root_layout.addWidget(self.adjustments_table)

        add_adjustment_button = QPushButton("إضافة تعديل خلطة")
        add_adjustment_button.clicked.connect(self.add_adjustment_row)
        remove_adjustment_button = QPushButton("حذف التعديل المحدد")
        remove_adjustment_button.setObjectName("dangerButton")
        remove_adjustment_button.clicked.connect(self.remove_adjustment_row)
        adjustment_actions = QHBoxLayout()
        adjustment_actions.addWidget(add_adjustment_button)
        adjustment_actions.addWidget(remove_adjustment_button)
        adjustment_actions.addStretch()
        root_layout.addLayout(adjustment_actions)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("تسجيل الناتج وإتمام الأمر")
        buttons.button(QDialogButtonBox.Cancel).setText("رجوع")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(root_widget)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll)

    def add_adjustment_row(self) -> None:
        row = self.adjustments_table.rowCount()
        self.adjustments_table.insertRow(row)

        material_input = QComboBox()
        material_input.addItem("اختر الخامة المستبعدة", None)
        for material in self.materials:
            material_input.addItem(
                f"{material['code']} — {material['name']}",
                int(material["product_id"]),
            )
        batch_input = QLineEdit("1")
        reason_input = QLineEdit()
        reason_input.setPlaceholderText("سبب الاستبعاد")
        quantities_button = QPushButton("تحديد الكميات")
        quantities_button.setObjectName("secondaryButton")
        quantities_button.clicked.connect(
            lambda _checked=False, button=quantities_button: self.edit_adjustment_quantities(button)
        )

        self.adjustments_table.setCellWidget(row, 0, material_input)
        self.adjustments_table.setCellWidget(row, 1, batch_input)
        self.adjustments_table.setCellWidget(row, 2, reason_input)
        self.adjustments_table.setCellWidget(row, 3, quantities_button)
        self.adjustment_quantities[row] = {}

    def remove_adjustment_row(self) -> None:
        row = self.adjustments_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر تعديلًا من الجدول")
            return
        old_values = dict(self.adjustment_quantities)
        self.adjustments_table.removeRow(row)
        self.adjustment_quantities = {}
        for old_row, values in old_values.items():
            if old_row < row:
                self.adjustment_quantities[old_row] = values
            elif old_row > row:
                self.adjustment_quantities[old_row - 1] = values

    def edit_adjustment_quantities(self, button: QPushButton) -> None:
        row = -1
        for index in range(self.adjustments_table.rowCount()):
            if self.adjustments_table.cellWidget(index, 3) is button:
                row = index
                break
        if row < 0:
            return
        material_input = self.adjustments_table.cellWidget(row, 0)
        batch_input = self.adjustments_table.cellWidget(row, 1)
        if not isinstance(material_input, QComboBox) or not isinstance(batch_input, QLineEdit):
            return
        if material_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر الخامة المستبعدة أولًا")
            return
        try:
            batch_count = int(batch_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "عدد الخلطات المعدلة يجب أن يكون رقمًا صحيحًا")
            return
        dialog = MaterialQuantitiesDialog(
            self.materials,
            excluded_product_id=int(material_input.currentData()),
            batch_count=batch_count,
            current=self.adjustment_quantities.get(row, {}),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.adjustment_quantities[row] = dialog.values()
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))

    def values(self) -> dict:
        try:
            actual_batches = int(self.actual_batches_input.text().strip())
            full_batches = int(self.full_batches_input.text().strip())
            modified_batches = int(self.modified_batches_input.text().strip())
            scrap_weight = float(self.scrap_input.text().strip() or 0)
            outputs = {}
            for product_id, fields in self.output_inputs.items():
                good, defective, actual_weight = fields
                outputs[product_id] = {
                    "good_quantity": float(good.text().strip() or 0),
                    "defective_quantity": float(defective.text().strip() or 0),
                    "actual_weight_kg": float(actual_weight.text().strip() or 0),
                }
        except ValueError as error:
            raise ValueError("أعداد الخلطات والإنتاج والأوزان يجب أن تكون أرقامًا") from error

        adjustments = []
        for row in range(self.adjustments_table.rowCount()):
            material_input = self.adjustments_table.cellWidget(row, 0)
            batch_input = self.adjustments_table.cellWidget(row, 1)
            reason_input = self.adjustments_table.cellWidget(row, 2)
            if not isinstance(material_input, QComboBox):
                continue
            if material_input.currentData() is None:
                raise ValueError("اختر الخامة المستبعدة في كل سطر تعديل")
            if not isinstance(batch_input, QLineEdit) or not isinstance(reason_input, QLineEdit):
                continue
            adjustments.append(
                {
                    "excluded_product_id": int(material_input.currentData()),
                    "batch_count": int(batch_input.text().strip()),
                    "reason": reason_input.text().strip(),
                    "actual_material_quantities": self.adjustment_quantities.get(row, {}),
                }
            )
        return {
            "actual_batches": actual_batches,
            "full_batches": full_batches,
            "modified_batches": modified_batches,
            "outputs": outputs,
            "scrap_weight": scrap_weight,
            "notes": self.notes_input.toPlainText().strip(),
            "adjustments": adjustments,
        }


class ProductionMixReportDialog(QDialog):
    def __init__(self, summary: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"تقرير خلطات التشغيل — {summary['order_number']}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(960, 620)

        form = QFormLayout()
        values = [
            ("عدد الخلطات المخطط", summary["planned_batches"]),
            ("عدد الخلطات الفعلي", summary["actual_batches"]),
            ("عدد الخلطات الكاملة", summary["full_batches"]),
            ("عدد الخلطات المعدلة", summary["modified_batches"]),
            ("الإنتاج السليم", f"{float(summary['good_output_quantity']):,.3f}"),
            ("الإنتاج المعيب", f"{float(summary['defective_output_quantity']):,.3f}"),
            ("الوزن الفعلي", f"{float(summary['actual_output_weight']):,.3f} كجم"),
            ("الهالك", f"{float(summary['scrap_weight']):,.3f} كجم"),
            ("تكلفة الخلطات الكاملة", f"{float(summary['full_mix_cost']):,.2f}"),
            ("تكلفة الخلطات المعدلة", f"{float(summary['modified_mix_cost']):,.2f}"),
            ("إجمالي تكلفة أمر التصنيع", f"{float(summary['total_cost']):,.2f}"),
        ]
        for label, value in values:
            form.addRow(label, QLabel(str(value)))

        table = QTableWidget(len(summary["adjustments"]), 5)
        table.setHorizontalHeaderLabels(
            ["الخامة المستبعدة", "عدد مرات الاستبعاد", "السبب", "كميات باقي الخامات", "التكلفة"]
        )
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        for row_index, adjustment in enumerate(summary["adjustments"]):
            row_values = [
                f"{adjustment['code']} — {adjustment['name']}",
                adjustment["excluded_batches"],
                adjustment["reason"],
                adjustment["actual_materials_text"],
                f"{float(adjustment['cost_amount']):,.2f}",
            ]
            for column, value in enumerate(row_values):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))

        notes = QLabel(str(summary.get("notes", "") or "—"))
        notes.setWordWrap(True)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("إغلاق")
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("تعديلات الخلطات"))
        layout.addWidget(table)
        layout.addWidget(QLabel("ملاحظات التشغيل"))
        layout.addWidget(notes)
        layout.addWidget(buttons)


class ProductionRunManufacturingPage(ReplannedManufacturingPage):
    """Original manufacturing flow with aggregate mix completion reporting."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        report_button = QPushButton("خلطات التشغيل")
        report_button.setObjectName("secondaryButton")
        report_button.clicked.connect(self.open_mix_report)
        page = self.orders_table.parentWidget()
        if page is not None and page.layout() is not None:
            page.layout().insertWidget(max(0, page.layout().count() - 1), report_button)

    def _complete_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            order = self.repository.get_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        dialog = ProductionCompletionDialog(order, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            values = dialog.values()
            result = self.repository.complete_order_with_mix_summary(
                order_id,
                **values,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الإتمام", str(error))
            return
        self._reload_orders()
        QMessageBox.information(
            self,
            "تم إتمام أمر التصنيع",
            f"إجمالي تكلفة الأمر: {float(result['total_cost']):,.2f}\n"
            f"الوزن الفعلي للإنتاج: {float(result['actual_output_weight']):,.3f} كجم\n"
            f"فرق الوزن الرقابي: {float(result['weight_variance']):,.3f} كجم",
        )

    def open_mix_report(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            summary = self.repository.get_mix_summary(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تقرير خلطات التشغيل", str(error))
            return
        ProductionMixReportDialog(summary, self).exec()


__all__ = [
    "ProductionRunManufacturingPage",
    "ProductionCompletionDialog",
    "ProductionMixReportDialog",
]
