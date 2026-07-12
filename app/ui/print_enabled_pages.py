from PySide6.QtWidgets import QMessageBox, QPushButton

from app.repositories.print_settings_repository import PrintSettingsRepository
from app.services.thermal_print_service import ThermalPrintService
from app.ui.accounting_order_pages import SalesAccountingPage
from app.ui.accounts_page import AccountsPage


class SalesAccountingPageWithPrint(SalesAccountingPage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._thermal_print_service = ThermalPrintService()

        print_button = QPushButton("معاينة وطباعة فاتورة الأمر المحدد")
        print_button.clicked.connect(self.preview_selected_invoice)
        self.layout().insertWidget(self.layout().count() - 1, print_button)

    def preview_selected_invoice(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return

        invoice = self.sales_repository.database.fetch_one(
            """
            SELECT id, status
            FROM sales_invoices
            WHERE sales_order_id = ?
            """,
            (order_id,),
        )
        if invoice is None:
            QMessageBox.warning(
                self,
                "تنبيه",
                "الأمر ما زال مسودة. سلّم الأمر أولًا لإنشاء فاتورة المبيعات.",
            )
            return
        if str(invoice["status"]) != "posted":
            QMessageBox.warning(self, "تنبيه", "يمكن طباعة الفاتورة المعتمدة فقط")
            return

        try:
            print_data = self.invoice_repository.get_sales_invoice_print_data(
                int(invoice["id"])
            )
            settings = PrintSettingsRepository(
                self.sales_repository.database
            ).get_settings()
            self._thermal_print_service.preview_sales_invoice(
                print_data,
                settings,
                self,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))


class AccountsPageWithPrint(AccountsPage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._thermal_print_service = ThermalPrintService()

        print_button = QPushButton("معاينة وطباعة فاتورة المبيعات")
        print_button.clicked.connect(self.preview_selected_sales_invoice)

        actions_item = self.sales_invoices_tab.layout().itemAt(1)
        actions_layout = None if actions_item is None else actions_item.layout()
        if actions_layout is not None:
            actions_layout.insertWidget(max(0, actions_layout.count() - 1), print_button)
        else:
            self.sales_invoices_tab.layout().insertWidget(2, print_button)

    def preview_selected_sales_invoice(self) -> None:
        row = self.sales_invoices_tab._selected()
        if row is None:
            return
        if str(row.get("status", "")) != "posted":
            QMessageBox.warning(self, "تنبيه", "يمكن طباعة الفاتورة المعتمدة فقط")
            return

        try:
            print_data = self.invoice_repository.get_sales_invoice_print_data(
                int(row["id"])
            )
            settings = PrintSettingsRepository(
                self.invoice_repository.database
            ).get_settings()
            self._thermal_print_service.preview_sales_invoice(
                print_data,
                settings,
                self,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))


__all__ = ["AccountsPageWithPrint", "SalesAccountingPageWithPrint"]