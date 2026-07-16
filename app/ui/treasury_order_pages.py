from PySide6.QtWidgets import QMessageBox, QPushButton

from app.repositories.quotation_repository import QuotationRepository
from app.repositories.treasury_invoice_repository import TreasuryInvoiceRepository
from app.ui.automated_purchase_page import AutomatedPurchaseAccountingPage
from app.ui.print_enabled_pages import SalesAccountingPageWithPrint
from app.ui.quotation_dialog import QuotationDialog


class _TreasuryOrderPageMixin:
    def _install_treasury_invoice_repository(self) -> None:
        database = (
            self.purchase_repository.database
            if hasattr(self, "purchase_repository")
            else self.sales_repository.database
        )
        self.invoice_repository = TreasuryInvoiceRepository(database)

    def _remove_order_entry_payment_field(self) -> None:
        paid_input = getattr(self, "paid_input", None)
        if paid_input is not None and paid_input.parentWidget() is not None:
            paid_input.parentWidget().hide()
        if paid_input is not None:
            paid_input.setText("0")

    def _hide_order_payment_buttons(self) -> None:
        for button in self.findChildren(QPushButton):
            text = button.text().strip()
            if "تسجيل سداد" in text or "تسجيل تحصيل" in text:
                button.hide()
                button.setEnabled(False)


class TreasuryPurchaseAccountingPage(
    _TreasuryOrderPageMixin, AutomatedPurchaseAccountingPage
):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_treasury_invoice_repository()
        self._remove_order_entry_payment_field()
        self._hide_order_payment_buttons()

    def create_order(self) -> None:
        if self.supplier_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر المورد")
            return
        try:
            order_id = self.purchase_repository.create_order_with_lines(
                supplier_id=int(self.supplier_input.currentData()),
                lines=self.lines,
                notes=self.notes_input.text(),
                paid_amount=0,
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.lines.clear()
        self.notes_input.clear()
        self.refresh_lines_table()
        self.invoice_repository._ensure_invoices()
        self.reload_orders()
        self._hide_order_payment_buttons()
        QMessageBox.information(
            self,
            "تم",
            f"تم حفظ أمر الشراء رقم {order_id} كمسودة بدون تسجيل دفعة",
        )


class TreasurySalesAccountingPageWithPrint(
    _TreasuryOrderPageMixin, SalesAccountingPageWithPrint
):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_treasury_invoice_repository()
        self._remove_order_entry_payment_field()
        self._hide_order_payment_buttons()
        self.quotation_repository = QuotationRepository(self.sales_repository.database)

        quotation_button = QPushButton("عروض الأسعار")
        quotation_button.clicked.connect(self.open_quotations)
        self.layout().insertWidget(0, quotation_button)

    def open_quotations(self) -> None:
        QuotationDialog(self.quotation_repository, self).exec()

    def create_order(self) -> None:
        if self.customer_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل")
            return
        try:
            order_id = self.sales_repository.create_order_with_lines(
                customer_id=int(self.customer_input.currentData()),
                lines=self.lines,
                notes=self.notes_input.text(),
                paid_amount=0,
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.lines.clear()
        self.notes_input.clear()
        self.refresh_lines_table()
        self.invoice_repository._ensure_invoices()
        self.reload_orders()
        self._hide_order_payment_buttons()
        QMessageBox.information(
            self,
            "تم",
            f"تم حفظ أمر البيع رقم {order_id} كمسودة بدون تسجيل تحصيل",
        )


__all__ = [
    "TreasuryPurchaseAccountingPage",
    "TreasurySalesAccountingPageWithPrint",
]
