from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton

from app.repositories.enhanced_manufacturing_repository import (
    EnhancedManufacturingRepository,
)
from app.ui.manufacturing_page import ManufacturingPage


class EnhancedManufacturingPage(ManufacturingPage):
    def __init__(self, *args, **kwargs) -> None:
        self.editing_recipe_id: int | None = None
        super().__init__(*args, **kwargs)
        self._install_recipe_actions()
        self._install_order_actions()

    def _install_recipe_actions(self) -> None:
        page = self.recipes_table.parentWidget()
        layout = page.layout()
        actions = QHBoxLayout()

        self.edit_recipe_button = QPushButton("تعديل الخلطة المحددة")
        self.edit_recipe_button.setObjectName("secondaryButton")
        self.edit_recipe_button.clicked.connect(self._load_selected_recipe)

        self.cancel_recipe_edit_button = QPushButton("إلغاء تعديل الخلطة")
        self.cancel_recipe_edit_button.setObjectName("secondaryButton")
        self.cancel_recipe_edit_button.clicked.connect(self._clear_recipe_editor)
        self.cancel_recipe_edit_button.setVisible(False)

        actions.addWidget(self.edit_recipe_button)
        actions.addWidget(self.cancel_recipe_edit_button)
        actions.addStretch()
        layout.insertLayout(max(0, layout.count() - 1), actions)
        self.recipes_table.doubleClicked.connect(self._load_selected_recipe)

    def _install_order_actions(self) -> None:
        page = self.orders_table.parentWidget()
        layout = page.layout()
        self.remove_order_button = QPushButton("إلغاء أو حذف أمر التصنيع المحدد")
        self.remove_order_button.setObjectName("dangerButton")
        self.remove_order_button.clicked.connect(self._remove_selected_order)
        layout.insertWidget(max(0, layout.count() - 1), self.remove_order_button)

    def _load_selected_recipe(self) -> None:
        row = self.recipes_table.currentRow()
        if row < 0 or row >= len(self.recipes):
            QMessageBox.warning(self, "تنبيه", "اختر خلطة من الجدول")
            return

        recipe_id = int(self.recipes[row]["id"])
        try:
            recipe = self.repository.get_recipe(recipe_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return

        self.editing_recipe_id = recipe_id
        self.recipe_code_input.setText(str(recipe["code"]))
        self.recipe_name_input.setText(str(recipe["name"]))
        self.recipe_notes_input.setText(str(recipe.get("notes", "") or ""))

        suggested_scrap = next(
            (
                float(component["quantity_per_batch"])
                for component in recipe["components"]
                if component["component_kind"] == "optional_scrap"
            ),
            0.0,
        )
        self.recipe_scrap_suggestion_input.setText(f"{suggested_scrap:g}")

        output_ids = {int(output["product_id"]) for output in recipe["outputs"]}
        self.recipe_outputs_list.clearSelection()
        for index in range(self.recipe_outputs_list.count()):
            item = self.recipe_outputs_list.item(index)
            item.setSelected(int(item.data(Qt.UserRole)) in output_ids)

        self.recipe_components = [
            {
                "product_id": int(component["product_id"]),
                "code": str(component["code"]),
                "name": str(component["name"]),
                "quantity_per_batch": float(component["quantity_per_batch"]),
            }
            for component in recipe["components"]
            if component["component_kind"] == "material"
        ]
        self._refresh_recipe_components()
        self.cancel_recipe_edit_button.setVisible(True)
        self._set_save_recipe_button_text("حفظ تعديلات الخلطة")
        self.recipe_code_input.setFocus()

    def _save_recipe(self) -> None:
        if self.editing_recipe_id is None:
            super()._save_recipe()
            return

        output_ids = [
            int(item.data(Qt.UserRole))
            for item in self.recipe_outputs_list.selectedItems()
        ]
        try:
            self.repository.update_recipe(
                self.editing_recipe_id,
                code=self.recipe_code_input.text(),
                name=self.recipe_name_input.text(),
                output_product_ids=output_ids,
                components=self.recipe_components,
                suggested_scrap_per_batch=float(
                    self.recipe_scrap_suggestion_input.text().strip() or 0
                ),
                notes=self.recipe_notes_input.text(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تعذر التعديل", str(error))
            return

        recipe_id = self.editing_recipe_id
        self._clear_recipe_editor(reload_page=False)
        self.reload()
        QMessageBox.information(self, "تم", f"تم تعديل الخلطة رقم {recipe_id}")

    def _clear_recipe_editor(self, *, reload_page: bool = False) -> None:
        self.editing_recipe_id = None
        self.recipe_code_input.clear()
        self.recipe_name_input.clear()
        self.recipe_notes_input.clear()
        self.recipe_scrap_suggestion_input.setText("0")
        self.recipe_outputs_list.clearSelection()
        self.recipe_components.clear()
        self._refresh_recipe_components()
        self.cancel_recipe_edit_button.setVisible(False)
        self._set_save_recipe_button_text("حفظ الخلطة")
        if reload_page:
            self.reload()

    def _set_save_recipe_button_text(self, text: str) -> None:
        page = self.recipes_table.parentWidget()
        for button in page.findChildren(QPushButton):
            if button.text() in {"حفظ الخلطة", "حفظ تعديلات الخلطة"}:
                button.setText(text)
                return

    def _remove_selected_order(self) -> None:
        row = self.orders_table.currentRow()
        if row < 0 or row >= len(self.orders):
            QMessageBox.warning(self, "تنبيه", "اختر أمر تصنيع من الجدول")
            return

        order = self.orders[row]
        order_id = int(order["id"])
        order_number = str(order["order_number"])
        status = str(order["status"])

        if status == "completed":
            QMessageBox.warning(
                self,
                "غير مسموح",
                "لا يمكن حذف أو إلغاء أمر مكتمل لأنه أثّر على المخزون والتكلفة.",
            )
            return
        if status == "cancelled":
            QMessageBox.information(self, "تنبيه", "أمر التصنيع ملغي بالفعل")
            return

        if status == "draft":
            question = (
                f"سيتم حذف أمر التصنيع {order_number} نهائيًا لأنه ما زال مسودة.\n"
                "هل تريد المتابعة؟"
            )
            answer = QMessageBox.question(
                self,
                "تأكيد حذف أمر التصنيع",
                question,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return
            try:
                self.repository.delete_draft_order(order_id)
            except ValueError as error:
                QMessageBox.warning(self, "تعذر الحذف", str(error))
                return
            self._reload_orders()
            QMessageBox.information(self, "تم", "تم حذف أمر التصنيع المسودة")
            return

        answer = QMessageBox.question(
            self,
            "تأكيد إلغاء أمر التصنيع",
            f"سيتم إلغاء الأمر {order_number} ورد جميع الخامات المصروفة للمخزون.\n"
            "سيظل الأمر ظاهرًا بالحالة «ملغي» للحفاظ على سجل العمليات.\n"
            "هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repository.cancel_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تعذر الإلغاء", str(error))
            return
        self._reload_orders()
        QMessageBox.information(
            self,
            "تم",
            "تم إلغاء أمر التصنيع ورد الخامات المصروفة إلى المخزون",
        )


__all__ = ["EnhancedManufacturingPage", "EnhancedManufacturingRepository"]
