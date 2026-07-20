from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.enhanced_manufacturing_page import EnhancedManufacturingPage


class MaterialAvailabilityDialog(QDialog):
    def __init__(self, rows: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("مراجعة توافر خامات أمر التصنيع")
        self.setLayoutDirection(Qt.RightToLeft)
        self.resize(760, 420)

        intro = QLabel(
            "راجع جميع الخامات مرة واحدة قبل الصرف. الكسر اختياري ولا يمنع البدء، "
            "أما أي عجز في خامة أساسية فيمنع صرف الأمر."
        )
        intro.setWordWrap(True)

        table = QTableWidget(len(rows), 5)
        table.setHorizontalHeaderLabels(["الخامة", "النوع", "المطلوب", "المتاح", "العجز"])
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        for row_index, row in enumerate(rows):
            values = [
                f"{row['code']} — {row['name']}",
                "كسر اختياري" if row["component_kind"] == "scrap" else "خامة أساسية",
                f"{float(row['required']):,.2f}",
                f"{float(row['available']):,.2f}",
                f"{float(row['shortage']):,.2f}",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column == 4 and float(row["shortage"]) > 0:
                    item.setToolTip(
                        "هذا العجز يمنع البدء"
                        if row["blocks_start"]
                        else "الكسر اختياري وسيصرف النظام المتاح فقط"
                    )
                table.setItem(row_index, column, item)
        table.resizeColumnsToContents()

        has_blocking = any(bool(row.get("blocks_start")) for row in rows)
        result_label = QLabel(
            "يوجد عجز في خامات أساسية — لا يمكن بدء الأمر."
            if has_blocking
            else "جميع الخامات الأساسية متاحة ويمكن بدء الأمر."
        )
        result_label.setStyleSheet("font-size: 16px; font-weight: 800;")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("إغلاق")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addWidget(table)
        layout.addWidget(result_label)
        layout.addWidget(buttons)


class AdvancedCompletionDialog(QDialog):
    def __init__(self, repository, order: dict, parent=None) -> None:
        super().__init__(parent)
        self.repository = repository
        self.order = order
        self.setWindowTitle(f"تسجيل الإنتاج الفعلي — {order['order_number']}")
        self.setLayoutDirection(Qt.RightToLeft)
        self.output_inputs: dict[int, QLineEdit] = {}

        intro = QLabel(
            "أدخل عدد الخلطات التي استُخدمت فعليًا وعدد المواسير السليمة. "
            "النظام يقترح الهالك تلقائيًا ويمكنك تأكيده أو تعديله."
        )
        intro.setWordWrap(True)

        form = QFormLayout()
        self.actual_batches_input = QLineEdit(str(int(order["actual_batches"])))
        self.actual_batches_input.setPlaceholderText("عدد الخلطات الفعلي")
        form.addRow("عدد الخلطات الفعلي", self.actual_batches_input)

        for output in order["outputs"]:
            field = QLineEdit(f"{float(output['planned_quantity']):g}")
            field.setPlaceholderText("عدد المواسير السليمة")
            self.output_inputs[int(output["product_id"])] = field
            form.addRow(
                f"{output['name']} — وزن {float(output['standard_weight_kg']):g} كجم",
                field,
            )
            field.editingFinished.connect(self.recalculate_scrap)

        self.scrap_input = QLineEdit("0")
        self.scrap_input.setPlaceholderText("كجم الهالك/الكسر المؤكد")
        form.addRow("الهالك/الكسر الناتج (كجم)", self.scrap_input)

        self.calculation_label = QLabel()
        self.calculation_label.setWordWrap(True)
        self.calculation_label.setStyleSheet(
            "font-size: 15px; font-weight: 700; padding: 8px; background: #0F2A4A;"
        )

        recalculate_button = QPushButton("إعادة حساب الهالك المقترح")
        recalculate_button.setObjectName("secondaryButton")
        recalculate_button.clicked.connect(self.recalculate_scrap)
        self.actual_batches_input.editingFinished.connect(self.recalculate_scrap)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("إتمام واستلام الإنتاج")
        buttons.button(QDialogButtonBox.Cancel).setText("رجوع")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(recalculate_button)
        layout.addWidget(self.calculation_label)
        layout.addWidget(buttons)
        self.recalculate_scrap()

    def _raw_values(self) -> tuple[int, dict[int, float]]:
        try:
            batches = int(self.actual_batches_input.text().strip())
            outputs = {
                product_id: float(field.text().strip() or 0)
                for product_id, field in self.output_inputs.items()
            }
        except ValueError as error:
            raise ValueError("عدد الخلطات والكميات الفعلية يجب أن تكون أرقامًا صحيحة") from error
        return batches, outputs

    def recalculate_scrap(self) -> None:
        try:
            batches, outputs = self._raw_values()
            suggestion = self.repository.suggested_scrap_quantity(
                int(self.order["id"]),
                actual_outputs=outputs,
                target_batches=batches,
            )
        except ValueError as error:
            self.calculation_label.setText(str(error))
            return
        self.scrap_input.setText(f"{suggestion:g}")
        self.calculation_label.setText(
            f"الهالك المقترح تلقائيًا: {suggestion:,.2f} كجم. "
            "راجع الرقم وعدّله عند الحاجة قبل الإتمام."
        )

    def values(self) -> tuple[int, dict[int, float], float]:
        batches, outputs = self._raw_values()
        try:
            scrap = float(self.scrap_input.text().strip() or 0)
        except ValueError as error:
            raise ValueError("الهالك المؤكد يجب أن يكون رقمًا") from error
        if scrap < 0:
            raise ValueError("الهالك المؤكد لا يمكن أن يكون سالبًا")
        return batches, outputs, scrap


class AdvancedManufacturingPage(EnhancedManufacturingPage):
    def __init__(self, *args, **kwargs) -> None:
        self.editing_order_id: int | None = None
        super().__init__(*args, **kwargs)
        self.remove_order_button.setText("تعديل أو حذف أو إلغاء أمر التصنيع المحدد")
        self._install_order_edit_controls()

    def _install_order_edit_controls(self) -> None:
        page = self.orders_table.parentWidget()
        layout = page.layout()
        self.cancel_order_edit_button = QPushButton("إلغاء تعديل أمر التصنيع")
        self.cancel_order_edit_button.setObjectName("secondaryButton")
        self.cancel_order_edit_button.setVisible(False)
        self.cancel_order_edit_button.clicked.connect(self._clear_order_editor)
        layout.insertWidget(max(0, layout.count() - 1), self.cancel_order_edit_button)

    def _save_order(self) -> None:
        if self.editing_order_id is None:
            super()._save_order()
            return
        recipe_id = self.order_recipe_input.currentData()
        warehouse_id = self.order_warehouse_input.currentData()
        if recipe_id is None or warehouse_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر الخلطة والمخزن")
            return
        if not self.order_outputs:
            QMessageBox.warning(self, "تنبيه", "أضف المواسير المطلوبة")
            return
        try:
            self.repository.update_draft_order(
                self.editing_order_id,
                recipe_id=int(recipe_id),
                warehouse_id=int(warehouse_id),
                outputs=self.order_outputs,
                scrap_inputs=self.order_scraps,
                notes=self.order_notes_input.text(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تعذر التعديل", str(error))
            return
        order_id = self.editing_order_id
        self._clear_order_editor(reload_orders=False)
        self._reload_orders()
        QMessageBox.information(self, "تم", f"تم تعديل أمر التصنيع رقم {order_id}")

    def _load_selected_order_for_edit(self) -> None:
        row = self.orders_table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختر أمر تصنيع من الجدول")
            return
        selected = self.orders[row]
        if selected["status"] != "draft":
            QMessageBox.warning(self, "غير مسموح", "يمكن تعديل أمر التصنيع وهو مسودة فقط")
            return
        order = self.repository.get_order(int(selected["id"]))
        self.editing_order_id = int(order["id"])

        self.order_recipe_input.blockSignals(True)
        recipe_index = self.order_recipe_input.findData(int(order["recipe_id"]))
        if recipe_index >= 0:
            self.order_recipe_input.setCurrentIndex(recipe_index)
        self.order_recipe_input.blockSignals(False)
        self._recipe_selected()

        warehouse_index = self.order_warehouse_input.findData(int(order["warehouse_id"]))
        if warehouse_index >= 0:
            self.order_warehouse_input.setCurrentIndex(warehouse_index)
        self.order_notes_input.setText(str(order.get("notes", "") or ""))

        self.order_outputs = [
            {
                "product_id": int(output["product_id"]),
                "name": str(output["name"]),
                "quantity": float(output["planned_quantity"]),
                "standard_weight_kg": float(output["standard_weight_kg"]),
            }
            for output in order["outputs"]
        ]
        scrap_stock = {
            int(row["product_id"]): row
            for row in self.repository.list_scrap_stock(int(order["warehouse_id"]))
        }
        self.order_scraps = []
        for material in order["materials"]:
            if material["component_kind"] != "scrap":
                continue
            stock = scrap_stock.get(int(material["product_id"]), {})
            self.order_scraps.append(
                {
                    "product_id": int(material["product_id"]),
                    "name": str(material["name"]),
                    "available": float(stock.get("available", 0)),
                    "quantity_per_batch": float(material["quantity_per_batch"]),
                }
            )
        self._refresh_order_lines()
        self.cancel_order_edit_button.setVisible(True)
        self._set_save_order_button_text("حفظ تعديلات أمر التصنيع")

    def _clear_order_editor(self, *, reload_orders: bool = False) -> None:
        self.editing_order_id = None
        self.order_outputs.clear()
        self.order_scraps.clear()
        self.order_notes_input.clear()
        self._refresh_order_lines()
        self.cancel_order_edit_button.setVisible(False)
        self._set_save_order_button_text("إنشاء أمر التصنيع كمسودة")
        if reload_orders:
            self._reload_orders()

    def _set_save_order_button_text(self, text: str) -> None:
        page = self.orders_table.parentWidget()
        for button in page.findChildren(QPushButton):
            if button.text() in {
                "إنشاء أمر التصنيع كمسودة",
                "حفظ تعديلات أمر التصنيع",
            }:
                button.setText(text)
                return

    def _remove_selected_order(self) -> None:
        row = self.orders_table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختر أمر تصنيع من الجدول")
            return
        order = self.orders[row]
        status = str(order["status"])
        if status == "draft":
            box = QMessageBox(self)
            box.setWindowTitle("إجراء على أمر التصنيع")
            box.setText("اختر الإجراء المطلوب لأمر التصنيع المسودة")
            edit_button = box.addButton("تعديل الأمر", QMessageBox.AcceptRole)
            delete_button = box.addButton("حذف الأمر", QMessageBox.DestructiveRole)
            box.addButton("رجوع", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() == edit_button:
                self._load_selected_order_for_edit()
                return
            if box.clickedButton() != delete_button:
                return
        super()._remove_selected_order()

    def _start_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            rows = self.repository.material_availability(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الفحص", str(error))
            return
        dialog = MaterialAvailabilityDialog(rows, self)
        dialog.exec()
        if self.repository.blocking_shortages(rows):
            return
        answer = QMessageBox.question(
            self,
            "تأكيد صرف الخامات",
            "جميع الخامات الأساسية متاحة. هل تريد صرفها وبدء أمر التصنيع؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repository.start_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر البدء", str(error))
            return
        self._reload_orders()
        QMessageBox.information(self, "تم", "تم صرف الخامات وبدء أمر التصنيع")

    def _complete_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            order = self.repository.get_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        dialog = AdvancedCompletionDialog(self.repository, order, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            batches, outputs, scrap = dialog.values()
            result = self.repository.complete_order_with_batches(
                order_id,
                actual_batches=batches,
                actual_outputs=outputs,
                returned_scrap_quantity=scrap,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الإتمام", str(error))
            return
        self._reload_orders()
        QMessageBox.information(
            self,
            "تم استلام الإنتاج",
            f"تكلفة الإنتاج التام: {result['finished_cost']:,.2f}\n"
            f"تكلفة كجم الهالك: {result['scrap_unit_cost']:,.4f}\n"
            f"فرق الوزن الرقابي: {result['weight_variance']:,.2f} كجم",
        )


__all__ = ["AdvancedManufacturingPage"]
