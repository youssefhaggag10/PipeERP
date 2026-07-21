from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSizePolicy,
)

from app.repositories.wizard_manufacturing_repository import WizardManufacturingRepository
from app.ui.final_production_completion_wizard import FinalProductionCompletionWizard
from app.ui.production_run_page import ProductionRunManufacturingPage


class FinalManufacturingPage(ProductionRunManufacturingPage):
    """One-time material issue followed by a simple aggregate completion wizard."""

    def __init__(self, repository, *args, **kwargs) -> None:
        validated_repository = WizardManufacturingRepository(repository.database)
        super().__init__(validated_repository, *args, **kwargs)
        self._remove_manual_batch_actions()
        self._align_order_action_buttons()

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
                button.setParent(None)
                button.deleteLater()

    def _align_order_action_buttons(self) -> None:
        labels = (
            "بدء وصرف الخامات",
            "تسجيل الناتج وإتمام الأمر",
            "تعديل أو حذف أو إلغاء أمر التصنيع المحدد",
            "خلطات التشغيل",
        )
        by_text = {
            button.text().strip(): button for button in self.findChildren(QPushButton)
        }
        buttons = [by_text[label] for label in labels if label in by_text]
        if not buttons:
            return

        page = self.orders_table.parentWidget()
        page_layout = page.layout() if page is not None else None
        if page_layout is None:
            return

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(10)
        for button in buttons:
            button.show()
            button.setMinimumWidth(0)
            button.setMinimumHeight(48)
            button.setMaximumHeight(48)
            button.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            actions.addWidget(button, 1)

        table_index = page_layout.indexOf(self.orders_table)
        page_layout.insertLayout(max(0, table_index), actions)
        self.order_action_buttons = buttons

    def _complete_selected(self) -> None:
        order_id = self._selected_order_id()
        if order_id is None:
            return
        try:
            order = self.repository.get_order(order_id)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return

        wizard = FinalProductionCompletionWizard(order, self)
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
