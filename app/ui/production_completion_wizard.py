from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

from app.services.production_completion_preview import calculate_completion_preview
from app.ui.production_run_page import MaterialQuantitiesDialog


class ProductionCompletionWizard(QWizard):
    PRODUCTION_PAGE = 0
    ADJUSTMENTS_PAGE = 1
    SUMMARY_PAGE = 2

    def __init__(self, order: dict, parent=None) -> None:
        super().__init__(parent)
        self.order = order
        self.materials = list(order["materials"])
        self.output_inputs: dict[int, tuple[QLineEdit, QLineEdit, QLineEdit]] = {}
        self.adjustment_quantities: dict[int, dict[int, float]] = {}
        self._last_values: dict | None = None

        self.setWindowTitle(f"تسجيل الناتج وإتمام الأمر — {order['order_number']}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(900, 650)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setPage(self.PRODUCTION_PAGE, self._production_page())
        self.setPage(self.ADJUSTMENTS_PAGE, self._adjustments_page())
        self.setPage(self.SUMMARY_PAGE, self._summary_page())
        self.setStartId(self.PRODUCTION_PAGE)
        self.setButtonText(QWizard.WizardButton.BackButton, "السابق")
        self.setButtonText(QWizard.WizardButton.NextButton, "التالي")
        self.setButtonText(
            QWizard.WizardButton.FinishButton,
            "إتمام الأمر واستلام الإنتاج",
        )
        self.setButtonText(QWizard.WizardButton.CancelButton, "رجوع")

    def _production_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("1 — الإنتاج الفعلي")
        page.setSubTitle(
            "سجل الناتج مرة واحدة. الخامات صُرفت عند بدء الأمر ولن تُصرف مرة أخرى."
        )
        info = QLabel(
            f"الخلطات المخططة: {int(self.order['planned_batches'])} — "
            f"الخلطات المصروفة: {int(self.order['actual_batches'])}"
        )
        info.setWordWrap(True)

        form = QFormLayout()
        self.actual_batches_input = QLineEdit(str(int(self.order["actual_batches"])))
        form.addRow("عدد الخلطات الفعلي", self.actual_batches_input)

        self.outputs_table = QTableWidget(len(self.order["outputs"]), 4)
        self.outputs_table.setHorizontalHeaderLabels(
            ["الصنف", "الإنتاج السليم", "الإنتاج المعيب", "وزن السليم (كجم)"]
        )
        self.outputs_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.outputs_table.setSelectionMode(QTableWidget.NoSelection)
        self.outputs_table.setMinimumHeight(190)
        for row_index, output in enumerate(self.order["outputs"]):
            product_id = int(output["product_id"])
            planned = float(output["planned_quantity"])
            standard_weight = float(output["standard_weight_kg"] or 0)
            self.outputs_table.setItem(
                row_index,
                0,
                QTableWidgetItem(
                    f"{output['code']} — {output['name']} — قياسي {standard_weight:g} كجم"
                ),
            )
            good = QLineEdit(f"{planned:g}")
            defective = QLineEdit("0")
            actual_weight = QLineEdit(f"{planned * standard_weight:g}")
            self.outputs_table.setCellWidget(row_index, 1, good)
            self.outputs_table.setCellWidget(row_index, 2, defective)
            self.outputs_table.setCellWidget(row_index, 3, actual_weight)
            self.output_inputs[product_id] = (good, defective, actual_weight)

        bottom_form = QFormLayout()
        self.scrap_input = QLineEdit("0")
        self.notes_input = QTextEdit()
        self.notes_input.setPlaceholderText("ملاحظات التشغيل")
        self.notes_input.setMaximumHeight(80)
        bottom_form.addRow("الهالك/الكسر (كجم)", self.scrap_input)
        bottom_form.addRow("ملاحظات التشغيل", self.notes_input)

        question = QLabel("هل تم تشغيل جميع الخلطات بنفس تركيبة الخامات؟")
        self.all_complete_radio = QRadioButton("نعم، جميع الخلطات كاملة")
        self.modified_radio = QRadioButton("لا، توجد خلطات معدلة")
        self.all_complete_radio.setChecked(True)

        layout = QVBoxLayout(page)
        layout.addWidget(info)
        layout.addLayout(form)
        layout.addWidget(QLabel("الإنتاج الفعلي لكل منتج"))
        layout.addWidget(self.outputs_table)
        layout.addLayout(bottom_form)
        layout.addWidget(question)
        layout.addWidget(self.all_complete_radio)
        layout.addWidget(self.modified_radio)
        layout.addStretch()
        return page

    def _adjustments_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("2 — مجموعات تعديل الخلطات")
        page.setSubTitle("أضف مجموعة لكل تعديل متشابه، وليس سجلًا لكل خلطة.")
        self.adjustments_table = QTableWidget(0, 4)
        self.adjustments_table.setHorizontalHeaderLabels(
            ["عدد الخلطات", "الخامة المستبعدة", "سبب الاستبعاد", "تفاصيل الكميات"]
        )
        self.adjustments_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.adjustments_table.setMinimumHeight(270)

        add_button = QPushButton("إضافة مجموعة تعديل")
        add_button.clicked.connect(self.add_adjustment_row)
        remove_button = QPushButton("حذف المجموعة المحددة")
        remove_button.setObjectName("dangerButton")
        remove_button.clicked.connect(self.remove_adjustment_row)
        actions = QHBoxLayout()
        actions.addWidget(add_button)
        actions.addWidget(remove_button)
        actions.addStretch()
        self.adjustments_totals_label = QLabel()

        layout = QVBoxLayout(page)
        layout.addWidget(self.adjustments_table)
        layout.addLayout(actions)
        layout.addWidget(self.adjustments_totals_label)
        layout.addStretch()
        return page

    def _summary_page(self) -> QWizardPage:
        page = QWizardPage()
        page.setTitle("3 — ملخص إتمام أمر التصنيع")
        page.setSubTitle("راجع التكلفة والخامات التي ستعود للمخزن قبل الحفظ.")
        form = QFormLayout()
        self.summary_labels: dict[str, QLabel] = {}
        fields = (
            ("full_batches", "عدد الخلطات الكاملة"),
            ("modified_batches", "عدد الخلطات المعدلة"),
            ("good_output_quantity", "الإنتاج السليم"),
            ("defective_output_quantity", "الإنتاج المعيب"),
            ("actual_output_weight", "الوزن الفعلي"),
            ("scrap_weight", "الهالك"),
            ("full_mix_cost", "تكلفة الخلطات الكاملة"),
            ("modified_mix_cost", "تكلفة الخلطات المعدلة"),
            ("total_cost", "إجمالي تكلفة الأمر"),
        )
        for key, title in fields:
            label = QLabel("—")
            self.summary_labels[key] = label
            form.addRow(title, label)

        self.material_summary_table = QTableWidget(0, 4)
        self.material_summary_table.setHorizontalHeaderLabels(
            ["الخامة", "المصروف", "المستهلك", "سيعاد للمخزن"]
        )
        self.material_summary_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.material_summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.material_summary_table.setSelectionMode(QTableWidget.NoSelection)
        self.material_summary_table.setMinimumHeight(210)

        layout = QVBoxLayout(page)
        layout.addLayout(form)
        layout.addWidget(QLabel("ملخص الخامات"))
        layout.addWidget(self.material_summary_table)
        layout.addStretch()
        return page

    def nextId(self) -> int:
        if self.currentId() == self.PRODUCTION_PAGE:
            return self.SUMMARY_PAGE if self.all_complete_radio.isChecked() else self.ADJUSTMENTS_PAGE
        if self.currentId() == self.ADJUSTMENTS_PAGE:
            return self.SUMMARY_PAGE
        return -1

    def validateCurrentPage(self) -> bool:
        try:
            if self.currentId() == self.PRODUCTION_PAGE:
                self._production_values()
            elif self.currentId() == self.ADJUSTMENTS_PAGE:
                self._last_values = self._values(include_adjustments=True)
            elif self.currentId() == self.SUMMARY_PAGE:
                self._last_values = self._values(
                    include_adjustments=self.modified_radio.isChecked()
                )
        except ValueError as error:
            QMessageBox.warning(self, "بيانات غير مكتملة", str(error))
            return False
        return True

    def initializePage(self, page_id: int) -> None:
        super().initializePage(page_id)
        if page_id == self.ADJUSTMENTS_PAGE:
            if self.adjustments_table.rowCount() == 0:
                self.add_adjustment_row()
            self._refresh_totals()
        elif page_id == self.SUMMARY_PAGE:
            try:
                self._last_values = self._values(
                    include_adjustments=self.modified_radio.isChecked()
                )
                preview = calculate_completion_preview(
                    materials=self.materials,
                    actual_batches=self._last_values["actual_batches"],
                    outputs=self._last_values["outputs"],
                    scrap_weight=self._last_values["scrap_weight"],
                    adjustments=self._last_values["adjustments"],
                )
            except ValueError as error:
                QMessageBox.warning(self, "تعذر إعداد الملخص", str(error))
                self.back()
                return
            self._fill_summary(preview)

    def add_adjustment_row(self) -> None:
        row = self.adjustments_table.rowCount()
        self.adjustments_table.insertRow(row)
        batch_input = QLineEdit("1")
        batch_input.editingFinished.connect(self._refresh_totals)
        material_input = QComboBox()
        material_input.addItem("اختر الخامة المستبعدة", None)
        for material in self.materials:
            material_input.addItem(
                f"{material['code']} — {material['name']}",
                int(material["product_id"]),
            )
        reason_input = QLineEdit()
        reason_input.setPlaceholderText("سبب الاستبعاد")
        quantities_button = QPushButton("تفاصيل الكميات")
        quantities_button.setObjectName("secondaryButton")
        quantities_button.clicked.connect(
            lambda _checked=False, button=quantities_button: self.edit_quantities(button)
        )
        self.adjustments_table.setCellWidget(row, 0, batch_input)
        self.adjustments_table.setCellWidget(row, 1, material_input)
        self.adjustments_table.setCellWidget(row, 2, reason_input)
        self.adjustments_table.setCellWidget(row, 3, quantities_button)
        self.adjustment_quantities[row] = {}
        self._refresh_totals()

    def remove_adjustment_row(self) -> None:
        row = self.adjustments_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر مجموعة تعديل من الجدول")
            return
        old_values = dict(self.adjustment_quantities)
        self.adjustments_table.removeRow(row)
        self.adjustment_quantities = {}
        for old_row, values in old_values.items():
            if old_row < row:
                self.adjustment_quantities[old_row] = values
            elif old_row > row:
                self.adjustment_quantities[old_row - 1] = values
        self._refresh_totals()

    def edit_quantities(self, button: QPushButton) -> None:
        row = next(
            (
                index
                for index in range(self.adjustments_table.rowCount())
                if self.adjustments_table.cellWidget(index, 3) is button
            ),
            -1,
        )
        if row < 0:
            return
        batch_input = self.adjustments_table.cellWidget(row, 0)
        material_input = self.adjustments_table.cellWidget(row, 1)
        if not isinstance(batch_input, QLineEdit) or not isinstance(material_input, QComboBox):
            return
        if material_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر الخامة المستبعدة أولًا")
            return
        try:
            batch_count = int(batch_input.text().strip())
            if batch_count <= 0:
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "عدد الخلطات المعدلة يجب أن يكون رقمًا موجبًا")
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

    def _production_values(self) -> dict:
        try:
            actual_batches = int(self.actual_batches_input.text().strip())
            scrap_weight = float(self.scrap_input.text().strip() or 0)
            outputs = {}
            for product_id, fields in self.output_inputs.items():
                good, defective, weight = fields
                outputs[product_id] = {
                    "good_quantity": float(good.text().strip() or 0),
                    "defective_quantity": float(defective.text().strip() or 0),
                    "actual_weight_kg": float(weight.text().strip() or 0),
                }
        except ValueError as error:
            raise ValueError("أعداد الخلطات والإنتاج والأوزان يجب أن تكون أرقامًا") from error
        if actual_batches <= 0:
            raise ValueError("عدد الخلطات الفعلي يجب أن يكون أكبر من صفر")
        issued_batches = int(self.order["actual_batches"])
        if actual_batches > issued_batches:
            raise ValueError(
                f"عدد الخلطات الفعلي لا يمكن أن يتجاوز الخلطات المصروفة ({issued_batches})"
            )
        return {
            "actual_batches": actual_batches,
            "outputs": outputs,
            "scrap_weight": scrap_weight,
            "notes": self.notes_input.toPlainText().strip(),
        }

    def _adjustments(self) -> list[dict]:
        result = []
        for row in range(self.adjustments_table.rowCount()):
            batch_input = self.adjustments_table.cellWidget(row, 0)
            material_input = self.adjustments_table.cellWidget(row, 1)
            reason_input = self.adjustments_table.cellWidget(row, 2)
            if not isinstance(batch_input, QLineEdit):
                continue
            if not isinstance(material_input, QComboBox) or material_input.currentData() is None:
                raise ValueError("اختر الخامة المستبعدة في كل مجموعة تعديل")
            if not isinstance(reason_input, QLineEdit):
                continue
            try:
                batch_count = int(batch_input.text().strip())
            except ValueError as error:
                raise ValueError("عدد الخلطات المعدلة يجب أن يكون رقمًا صحيحًا") from error
            if batch_count <= 0:
                raise ValueError("عدد الخلطات المعدلة في كل مجموعة يجب أن يكون أكبر من صفر")
            reason = reason_input.text().strip()
            if not reason:
                raise ValueError("اكتب سبب استبعاد الخامة في كل مجموعة تعديل")
            result.append(
                {
                    "excluded_product_id": int(material_input.currentData()),
                    "batch_count": batch_count,
                    "reason": reason,
                    "actual_material_quantities": self.adjustment_quantities.get(row, {}),
                }
            )
        if not result:
            raise ValueError("أضف مجموعة تعديل واحدة على الأقل")
        return result

    def _values(self, *, include_adjustments: bool) -> dict:
        values = self._production_values()
        adjustments = self._adjustments() if include_adjustments else []
        modified_batches = sum(int(item["batch_count"]) for item in adjustments)
        full_batches = int(values["actual_batches"]) - modified_batches
        if full_batches < 0:
            raise ValueError("مجموع الخلطات المعدلة لا يمكن أن يتجاوز عدد الخلطات الفعلي")
        values.update(
            {
                "full_batches": full_batches,
                "modified_batches": modified_batches,
                "adjustments": adjustments,
            }
        )
        calculate_completion_preview(
            materials=self.materials,
            actual_batches=values["actual_batches"],
            outputs=values["outputs"],
            scrap_weight=values["scrap_weight"],
            adjustments=adjustments,
        )
        return values

    def _refresh_totals(self) -> None:
        try:
            actual = int(self.actual_batches_input.text().strip())
        except ValueError:
            actual = 0
        modified = 0
        for row in range(self.adjustments_table.rowCount()):
            field = self.adjustments_table.cellWidget(row, 0)
            if isinstance(field, QLineEdit):
                try:
                    modified += max(0, int(field.text().strip()))
                except ValueError:
                    pass
        self.adjustments_totals_label.setText(
            f"الخلطات الكاملة المحسوبة تلقائيًا: {actual - modified} — "
            f"الخلطات المعدلة: {modified} — الإجمالي: {actual}"
        )

    def _fill_summary(self, preview: dict) -> None:
        display = {
            "full_batches": str(preview["full_batches"]),
            "modified_batches": str(preview["modified_batches"]),
            "good_output_quantity": f"{float(preview['good_output_quantity']):,.3f}",
            "defective_output_quantity": f"{float(preview['defective_output_quantity']):,.3f}",
            "actual_output_weight": f"{float(preview['actual_output_weight']):,.3f} كجم",
            "scrap_weight": f"{float(preview['scrap_weight']):,.3f} كجم",
            "full_mix_cost": f"{float(preview['full_mix_cost']):,.2f}",
            "modified_mix_cost": f"{float(preview['modified_mix_cost']):,.2f}",
            "total_cost": f"{float(preview['total_cost']):,.2f}",
        }
        for key, text in display.items():
            self.summary_labels[key].setText(text)
        materials = list(preview["materials"])
        self.material_summary_table.setRowCount(len(materials))
        for row_index, material in enumerate(materials):
            row_values = [
                f"{material['code']} — {material['name']}",
                f"{float(material['issued']):,.3f}",
                f"{float(material['used']):,.3f}",
                f"{float(material['unused']):,.3f}",
            ]
            for column, value in enumerate(row_values):
                self.material_summary_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(value),
                )

    def values(self) -> dict:
        return self._values(include_adjustments=self.modified_radio.isChecked())

    def preview(self) -> dict:
        values = self.values()
        return calculate_completion_preview(
            materials=self.materials,
            actual_batches=values["actual_batches"],
            outputs=values["outputs"],
            scrap_weight=values["scrap_weight"],
            adjustments=values["adjustments"],
        )


__all__ = ["ProductionCompletionWizard"]
