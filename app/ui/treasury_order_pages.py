from PySide6.QtWidgets import QInputDialog, QMessageBox

from app.repositories.treasury_invoice_repository import TreasuryInvoiceRepository
from app.ui.automated_purchase_page import AutomatedPurchaseAccountingPage
from app.ui.payment_account_selector import (
    choose_financial_account,
    choose_payment_method,
)
from app.ui.print_enabled_pages import SalesAccountingPageWithPrint


class _TreasuryOrderPaymentMixin:
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

    def _record_selected_payment(self, invoice_type: str) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        self.invoice_repository._ensure_invoices()
        if invoice_type == "sales":
            row = self.sales_repository.database.fetch_one(
                "SELECT id, status, total FROM sales_invoices WHERE sales_order_id = ?",
                (order_id,),
            )
            action_label = "تحصيل"
        else:
            row = self.purchase_repository.database.fetch_one(
                "SELECT id, status, total FROM purchase_invoices WHERE purchase_order_id = ?",
                (order_id,),
            )
            action_label = "سداد"
        if row is None:
            QMessageBox.warning(self, "تنبيه", "لم يتم العثور على فاتورة مرتبطة بالأمر")
            return
        if row["status"] == "draft":
            self.invoice_repository.post_invoice(invoice_type, int(row["id"]))
        invoices = self.invoice_repository.list_invoices(invoice_type)
        invoice = next(
            (item for item in invoices if int(item["id"]) == int(row["id"])),
            None,
        )
        if invoice is None:
            return
        remaining = float(invoice["remaining"])
        if remaining <= 0.000001:
            QMessageBox.information(self, "تنبيه", "الفاتورة مدفوعة بالكامل")
            return
        amount, accepted = QInputDialog.getDouble(
            self,
            f"تسجيل {action_label}",
            f"المتبقي: {remaining:,.2f}\nأدخل المبلغ:",
            value=remaining,
            minValue=0.01,
            maxValue=remaining,
            decimals=2,
        )
        if not accepted:
            return
        method = choose_payment_method(self)
        if method is None:
            return
        account_id = choose_financial_account(self, self.invoice_repository, method)
        if account_id is None:
            return
        try:
            self.invoice_repository.record_invoice_payment(
                invoice_type=invoice_type,
                invoice_id=int(row["id"]),
                amount=float(amount),
                payment_method=method,
                financial_account_id=account_id,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload_orders()
        QMessageBox.information(
            self,
            "تم",
            f"تم تسجيل {action_label} على الحساب المالي المحدد وربطه بالفاتورة",
        )


class TreasuryPurchaseAccountingPage(
    _TreasuryOrderPaymentMixin, AutomatedPurchaseAccountingPage
):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_treasury_invoice_repository()
        self._remove_order_entry_payment_field()

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
        QMessageBox.information(
            self,
            "تم",
            f"تم حفظ أمر الشراء رقم {order_id} كمسودة بدون تسجيل دفعة",
        )


class TreasurySalesAccountingPageWithPrint(
    _TreasuryOrderPaymentMixin, SalesAccountingPageWithPrint
):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_treasury_invoice_repository()
        self._remove_order_entry_payment_field()

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
        QMessageBox.information(
            self,
            "تم",
            f"تم حفظ أمر البيع رقم {order_id} كمسودة بدون تسجيل تحصيل",
        )


__all__ = [
    "TreasuryPurchaseAccountingPage",
    "TreasurySalesAccountingPageWithPrint",
]
