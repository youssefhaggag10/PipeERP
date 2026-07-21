from __future__ import annotations

from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

from app.ui.production_completion_wizard import ProductionCompletionWizard
from app.ui.production_run_page import ProductionRunManufacturingPage


class FinalManufacturingPage(ProductionRunManufacturingPage):
    """One-time material issue followed by a simple aggregate completion wizard."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._remove_manual_batch_actions()

    def _remove_manual_batch_actions(self) -> None:
        forbidden = {
            "إضافة خلطة للأمر الجاري",
            "إنشاء/فتح الخلطة الحالية",
            "خلطة جديدة من السابقة بدون خامة",
            "إنشاء خلطة جديدة",
            "نسخ الخلطة الحالية",
            "إضافة خلطة كاملة",
        }
        for button in self.findChildren(QPushButton):
            if button.text().strip() in forbidden:
                button.hide()
                button.setEnabled(False)

    def _complete_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            order = self.repository.get_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return

        wizard = ProductionCompletionWizard(order, self)
        if wizard.exec() != QDialog.Accepted:
            return
        try:
            result = self.repository.complete_order_with_mix_summary(
                order_id,
                **wizard.values(),
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


__all__ = ["FinalManufacturingPage"]
