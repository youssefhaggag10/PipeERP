from PySide6.QtWidgets import QHBoxLayout, QInputDialog, QMessageBox, QPushButton

from app.repositories.print_settings_repository import PrintSettingsRepository
from app.services.a4_print_service import A4PrintService
from app.ui.accounting_order_pages import SalesAccountingPage
from app.ui.accounts_page import AccountsPage


class SalesAccountingPageWithPrint(SalesAccountingPage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Collections must be recorded through the controlled invoice/payment
        # workflow so the payment method and treasury/bank account are explicit.
        self.paid_input.setText("0")
        payment_container = self.paid_input.parentWidget()
        if payment_container is not None:
            payment_container.hide()

        self._invoice_print_service = A4PrintService()

        print_button = QPushButton("معاينة وطباعة فاتورة المبيعات A4")
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
            self._invoice_print_service.preview_sales_invoice(
                print_data,
                settings,
                self,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))


class AccountsPageWithPrint(AccountsPage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._invoice_print_service = A4PrintService()

        print_button = QPushButton("معاينة وطباعة فاتورة المبيعات A4")
        print_button.clicked.connect(self.preview_selected_sales_invoice)

        actions_item = self.sales_invoices_tab.layout().itemAt(1)
        actions_layout = None if actions_item is None else actions_item.layout()
        if actions_layout is not None:
            actions_layout.insertWidget(max(0, actions_layout.count() - 1), print_button)
        else:
            self.sales_invoices_tab.layout().insertWidget(2, print_button)

        reverse_button = QPushButton("عكس الحركة المالية المحددة")
        reverse_button.setObjectName("dangerButton")
        reverse_button.clicked.connect(self.reverse_selected_payment)
        reverse_actions = QHBoxLayout()
        reverse_actions.addWidget(reverse_button)
        reverse_actions.addStretch()
        transactions_widget = self.transactions_table.parentWidget()
        if transactions_widget is not None and transactions_widget.layout() is not None:
            transactions_widget.layout().insertLayout(2, reverse_actions)

    def reverse_selected_payment(self) -> None:
        row_index = self.transactions_table.currentRow()
        if row_index < 0:
            QMessageBox.warning(self, "تنبيه", "اختر حركة مالية من الجدول")
            return
        rows = self.accounting_repository.list_transactions()
        if row_index >= len(rows):
            QMessageBox.warning(self, "تنبيه", "تعذر تحديد الحركة المختارة")
            return
        row = rows[row_index]
        transaction_id = int(row.get("id", 0))
        if transaction_id <= 0:
            QMessageBox.information(self, "تنبيه", "الحركة المختارة هي حركة عكس بالفعل")
            return

        reason, accepted = QInputDialog.getText(
            self,
            "سبب عكس الحركة",
            "اكتب سبب العكس أو التصحيح:",
        )
        if not accepted:
            return
        answer = QMessageBox.question(
            self,
            "تأكيد عكس الحركة",
            f"سيتم عكس الحركة {row.get('transaction_number', '')} بقيمة "
            f"{float(row.get('amount', 0)):,.2f} مع الاحتفاظ بسجلها. هل تريد المتابعة؟",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.accounting_repository.reverse_payment(transaction_id, reason)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم عكس الحركة وتحديث الأرصدة والفواتير")

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
            self._invoice_print_service.preview_sales_invoice(
                print_data,
                settings,
                self,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))


__all__ = ["AccountsPageWithPrint", "SalesAccountingPageWithPrint"]
