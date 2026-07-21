from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QMessageBox,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
)

from app.repositories.customer_statement_accounting_repository import (
    CustomerStatementAccountingRepository,
)
from app.ui.clickable_summary_accounts_page import ClickableSummaryAccountsPage
from app.ui.customer_payment_allocation_dialog import CustomerPaymentAllocationDialog
from app.ui.customer_statement_page import CustomerStatementPage

MULTI_INVOICE_VALUE = "__multiple_invoices__"
INVOICE_ID_ROLE = Qt.ItemDataRole.UserRole + 2


class ResponsiveAccountsPage(ClickableSummaryAccountsPage):
    """Responsive accounts page with customer statements and invoice allocations."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.customer_statement_repository = CustomerStatementAccountingRepository(
            self.accounting_repository.database
        )
        self._install_customer_statement_tab()
        self._configure_financial_controls()
        self._make_treasury_tab_scrollable()
        self._reload_open_orders()

    def _main_tabs(self) -> QTabWidget | None:
        for tabs in self.findChildren(QTabWidget):
            if tabs.count() and tabs.tabText(0).strip() == "الملخص":
                return tabs
        return None

    def _install_customer_statement_tab(self) -> None:
        tabs = self._main_tabs()
        if tabs is None:
            return
        self.customer_statement_page = CustomerStatementPage(
            self.customer_statement_repository,
            self.partner_repository,
            self,
        )
        tabs.addTab(self.customer_statement_page, "كشف حساب العميل")

    def reload(self) -> None:
        super().reload()
        statement_page = getattr(self, "customer_statement_page", None)
        if statement_page is not None:
            statement_page.reload()

    def _reload_open_orders(self) -> None:
        transaction_type = str(self.transaction_type.currentData())
        if transaction_type != "customer_receipt":
            super()._reload_open_orders()
            return

        partner_id = self.partner_input.currentData()
        self.order_input.blockSignals(True)
        self.order_input.clear()
        self.order_input.addItem("دفعة عامة على حساب العميل", None)
        self.order_input.setItemData(0, 0.0, Qt.ItemDataRole.UserRole + 1)
        if partner_id is not None:
            invoices = self.customer_statement_repository.list_open_sales_invoices(
                int(partner_id)
            )
            if invoices:
                self.order_input.addItem(
                    "توزيع التحصيل على عدة فواتير…",
                    MULTI_INVOICE_VALUE,
                )
                self.order_input.setItemData(
                    self.order_input.count() - 1,
                    0.0,
                    Qt.ItemDataRole.UserRole + 1,
                )
            for invoice in invoices:
                invoice_type = (
                    "وزن"
                    if str(invoice["invoice_type"]) == "weight"
                    else "بيع عادي"
                )
                self.order_input.addItem(
                    f"{invoice['invoice_number']} — {invoice_type} — "
                    f"المتبقي {float(invoice['remaining']):,.2f}",
                    int(invoice["sales_order_id"]),
                )
                index = self.order_input.count() - 1
                self.order_input.setItemData(
                    index,
                    float(invoice["remaining"]),
                    Qt.ItemDataRole.UserRole + 1,
                )
                self.order_input.setItemData(
                    index,
                    int(invoice["id"]),
                    INVOICE_ID_ROLE,
                )
        self.order_input.blockSignals(False)
        self._fill_selected_remaining()

    def _fill_selected_remaining(self) -> None:
        if str(self.transaction_type.currentData()) != "customer_receipt":
            super()._fill_selected_remaining()
            return
        selected = self.order_input.currentData()
        if selected is None:
            return
        if selected == MULTI_INVOICE_VALUE:
            self.amount_input.clear()
            self.amount_input.setPlaceholderText("أدخل إجمالي مبلغ التحصيل ثم وزعه")
            return
        remaining = self.order_input.currentData(Qt.ItemDataRole.UserRole + 1)
        if remaining is not None:
            self.amount_input.setText(f"{float(remaining):.2f}")

    def save_payment(self) -> None:
        if str(self.transaction_type.currentData()) != "customer_receipt":
            super().save_payment()
            return
        if self.partner_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل")
            return
        if self.financial_account_input.currentData() is None:
            QMessageBox.warning(
                self,
                "تنبيه",
                "اختر حساب الخزينة أو البنك المناسب لطريقة الدفع",
            )
            return
        try:
            amount = float(self.amount_input.text().strip())
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "أدخل مبلغ تحصيل صحيح")
            return
        if amount <= 0:
            QMessageBox.warning(self, "تنبيه", "مبلغ التحصيل يجب أن يكون أكبر من صفر")
            return

        selected = self.order_input.currentData()
        allocations: list[dict] = []
        if selected == MULTI_INVOICE_VALUE:
            invoices = self.customer_statement_repository.list_open_sales_invoices(
                int(self.partner_input.currentData())
            )
            dialog = CustomerPaymentAllocationDialog(invoices, amount, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            allocations = dialog.allocations()
        elif selected is not None:
            invoice_id = self.order_input.currentData(INVOICE_ID_ROLE)
            if invoice_id is None:
                QMessageBox.warning(self, "تنبيه", "تعذر تحديد الفاتورة المختارة")
                return
            allocations = [
                {
                    "sales_invoice_id": int(invoice_id),
                    "amount": amount,
                }
            ]

        try:
            self.customer_statement_repository.record_customer_receipt_allocated(
                customer_id=int(self.partner_input.currentData()),
                amount=amount,
                payment_method=self.method_input.currentText(),
                financial_account_id=int(self.financial_account_input.currentData()),
                allocations=allocations,
                notes=self.notes_input.text(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return

        self.amount_input.clear()
        self.notes_input.clear()
        self.reload()
        QMessageBox.information(
            self,
            "تم",
            "تم تسجيل التحصيل وحفظ توزيعه على الفواتير المختارة.",
        )

    def _configure_financial_controls(self) -> None:
        for name, minimum_width in (
            ("account_code_input", 180),
            ("account_name_input", 240),
            ("opening_balance_input", 180),
            ("account_notes_input", 240),
        ):
            widget = getattr(self, name, None)
            if widget is None:
                continue
            widget.setMinimumWidth(minimum_width)
            widget.setMaximumWidth(16777215)
            widget.setMinimumHeight(38)
            widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        account_type = getattr(self, "account_type_input", None)
        if account_type is not None:
            account_type.setMinimumWidth(180)
            account_type.setMaximumWidth(16777215)
            account_type.setMinimumHeight(38)
            account_type.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        for table_name, minimum_height in (
            ("accounts_table", 230),
            ("movements_table", 300),
            ("transactions_table", 280),
        ):
            table = getattr(self, table_name, None)
            if table is None:
                continue
            table.setMinimumHeight(minimum_height)
            table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setStretchLastSection(True)

        for layout in self.findChildren(QFormLayout):
            layout.setFieldGrowthPolicy(
                QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
            )
            layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
            layout.setFormAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
            layout.setLabelAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            layout.setHorizontalSpacing(12)
            layout.setVerticalSpacing(10)

    def _make_treasury_tab_scrollable(self) -> None:
        tabs = self._main_tabs()
        if tabs is None:
            return
        treasury_index = -1
        for index in range(tabs.count()):
            if tabs.tabText(index).strip() == "الخزينة والبنوك":
                treasury_index = index
                break
        if treasury_index < 0:
            return

        treasury_widget = tabs.widget(treasury_index)
        if treasury_widget is None or isinstance(treasury_widget, QScrollArea):
            return
        current_index = tabs.currentIndex()
        title = tabs.tabText(treasury_index)
        icon = tabs.tabIcon(treasury_index)
        tooltip = tabs.tabToolTip(treasury_index)

        treasury_widget.setMinimumSize(0, 0)
        treasury_widget.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        scroll = QScrollArea()
        scroll.setObjectName("treasuryAccountsScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(treasury_widget)

        tabs.removeTab(treasury_index)
        tabs.insertTab(treasury_index, scroll, icon, title)
        tabs.setTabToolTip(treasury_index, tooltip)
        tabs.setCurrentIndex(current_index)


__all__ = ["ResponsiveAccountsPage"]
