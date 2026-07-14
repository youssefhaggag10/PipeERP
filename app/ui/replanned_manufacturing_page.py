from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from app.ui.advanced_manufacturing_page import AdvancedManufacturingPage
from app.ui.manufacturing_page import STATUS_LABELS


class ReplannedAvailabilityDialog(QDialog):
    def __init__(self, rows: list[dict], plan: dict, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("مراجعة وإعادة تخطيط خامات أمر التصنيع")
        self.resize(900, 500)

        if plan["changed"]:
            plan_text = (
                f"الكسر المتاح أقل من الكمية المخططة، لذلك سيعدل النظام عدد الخلطات "
                f"من {plan['old_batches']} إلى {plan['new_batches']} خلطة بعد موافقتك.\n"
                f"الكسر الذي سيُستخدم فعليًا: {plan['usable_scrap']:,.2f} كجم — "
                f"إجمالي الداخل بعد التعديل: {plan['planned_input_weight']:,.2f} كجم — "
                f"الزيادة المتوقعة: {plan['expected_overage_weight']:,.2f} كجم."
            )
        else:
            plan_text = (
                f"خطة التشغيل مناسبة للرصد الحالي: {plan['new_batches']} خلطة — "
                f"الكسر الذي سيُستخدم فعليًا: {plan['usable_scrap']:,.2f} كجم — "
                f"الزيادة المتوقعة: {plan['expected_overage_weight']:,.2f} كجم."
            )
        summary = QLabel(plan_text)
        summary.setWordWrap(True)
        summary.setStyleSheet(
            "font-size: 15px; font-weight: 800; padding: 10px; background: #0F2A4A;"
        )

        intro = QLabel(
            "يعرض الجدول كل الخامات مرة واحدة وفق الخطة المقترحة. "
            "العجز في خامة أساسية يمنع البدء، أما الكسر فيُصرف منه المتاح فعليًا."
        )
        intro.setWordWrap(True)

        table = QTableWidget(len(rows), 6)
        table.setHorizontalHeaderLabels(
            ["الخامة", "النوع", "المطلوب", "المتاح", "سيُصرف فعليًا", "العجز"]
        )
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        for row_index, row in enumerate(rows):
            is_scrap = row["component_kind"] == "scrap"
            will_issue = float(
                row.get(
                    "will_issue",
                    min(float(row["required"]), float(row["available"]))
                    if is_scrap
                    else float(row["required"]),
                )
            )
            values = [
                f"{row['code']} — {row['name']}",
                "كسر اختياري" if is_scrap else "خامة أساسية",
                f"{float(row['required']):,.2f}",
                f"{float(row['available']):,.2f}",
                f"{will_issue:,.2f}",
                f"{float(row['shortage']):,.2f}",
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))
        table.resizeColumnsToContents()

        has_blocking = any(bool(row.get("blocks_start")) for row in rows)
        result = QLabel(
            "يوجد عجز في خامات أساسية — لا يمكن بدء الأمر."
            if has_blocking
            else "الخطة المقترحة مغطاة ويمكن صرف الخامات وبدء الأمر."
        )
        result.setStyleSheet("font-size: 16px; font-weight: 800;")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("إغلاق")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.addWidget(summary)
        layout.addWidget(intro)
        layout.addWidget(table)
        layout.addWidget(result)
        layout.addWidget(buttons)


class ReplannedManufacturingPage(AdvancedManufacturingPage):
    """Manufacturing page with stock-aware scrap replanning and costing visibility."""

    def _reload_orders(self) -> None:
        self.orders = self.repository.list_orders()
        self.orders_table.setColumnCount(11)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر",
                "الخلطة",
                "المطلوب",
                "المخطط",
                "الفعلي",
                "الحالة",
                "تكلفة الخامات",
                "كمية الكسر الناتج (كجم)",
                "تكلفة كجم الكسر الناتج",
                "تكلفة الإنتاج التام بعد خصم الكسر",
                "فرق الوزن",
            ]
        )
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            completed = str(order["status"]) == "completed"
            returned_scrap_quantity = float(
                order.get("returned_scrap_quantity", 0) or 0
            )
            scrap_quantity = (
                f"{returned_scrap_quantity:,.2f}" if completed else "—"
            )
            scrap_unit_cost = (
                f"{float(order.get('scrap_unit_cost', 0) or 0):,.4f}"
                if completed and returned_scrap_quantity > 0
                else "—"
            )
            finished_cost = (
                f"{float(order['finished_cost']):,.2f}" if completed else "—"
            )
            values = [
                order["order_number"],
                order["recipe_name"],
                order["output_summary"],
                order["planned_batches"],
                order["actual_batches"],
                STATUS_LABELS.get(str(order["status"]), order["status"]),
                f"{float(order['material_cost']):,.2f}",
                scrap_quantity,
                scrap_unit_cost,
                finished_cost,
                f"{float(order['weight_variance']):,.2f}",
            ]
            for column, value in enumerate(values):
                self.orders_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _start_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            plan = self.repository.preview_replan_for_available_scrap(order_id)
            rows = self.repository.material_availability(
                order_id, target_batches=int(plan["new_batches"])
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تعذر الفحص", str(error))
            return

        ReplannedAvailabilityDialog(rows, plan, self).exec()
        if self.repository.blocking_shortages(rows):
            return

        confirmation = (
            f"سيبدأ الأمر على {plan['new_batches']} خلطة، وسيُصرف فعليًا "
            f"{plan['usable_scrap']:,.2f} كجم كسر. هل تريد المتابعة؟"
        )
        answer = QMessageBox.question(
            self,
            "تأكيد صرف الخامات",
            confirmation,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            self.repository.apply_replan(order_id, int(plan["new_batches"]))
            self.repository.start_order(order_id)
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تعذر البدء", str(error))
            self._reload_orders()
            return

        self._reload_orders()
        QMessageBox.information(
            self,
            "تم",
            f"تم صرف الخامات وبدء الأمر على {plan['new_batches']} خلطة",
        )


__all__ = ["ReplannedManufacturingPage"]