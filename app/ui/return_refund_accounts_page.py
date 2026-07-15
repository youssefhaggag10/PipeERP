from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from app.ui.strict_treasury_accounts_page import StrictTreasuryAccountsPage


class ReturnRefundAccountsPage(StrictTreasuryAccountsPage):
    """Central money screen including refunds caused by invoice returns."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.transaction_type.addItem("استرداد من مورد", "supplier_refund")
        self.transaction_type.addItem("رد مبلغ لعميل", "customer_refund")
        self._refresh_payment_form()

    def _current_partner_type(self) -> str:
        transaction_type = str(self.transaction_type.currentData())
        if transaction_type in {"customer_receipt", "customer_refund"}:
            return "customer"
        return "supplier"

    def _is_refund_mode(self) -> bool:
        return str(self.transaction_type.currentData()) in {
            "supplier_refund",
            "customer_refund",
        }

    def _reload_payment_partners(self) -> None:
        partner_type = self._current_partner_type()
        placeholder = "اختر العميل" if partner_type == "customer" else "اختر المورد"
        selected = self.partner_input.currentData()

        self.partner_input.blockSignals(True)
        self.partner_input.clear()
        self.partner_input.addItem(placeholder, None)
        for partner in self.partner_repository.list_partners(partner_type):
            label = str(partner["name"])
            code = str(partner.get("code") or "").strip()
            if code:
                label = f"{label} — {code}"
            self.partner_input.addItem(label, int(partner["id"]))
        if selected is not None:
            index = self.partner_input.findData(selected)
            if index >= 0:
                self.partner_input.setCurrentIndex(index)
        self.partner_input.blockSignals(False)
        self._reload_open_orders()

    def _reload_open_orders(self) -> None:
        partner_id = self.partner_input.currentData()
        transaction_type = str(self.transaction_type.currentData())

        self.order_input.blockSignals(True)
        self.order_input.clear()

        if self._is_refund_mode():
            self.order_input.addItem("اختر الفاتورة المرتجعة", None)
            self.order_input.setItemData(0, 0.0, Qt.UserRole + 1)
            if partner_id is not None:
                rows = self.accounting_repository.list_refundable_invoices(
                    transaction_type,
                    int(partner_id),
                )
                for row in rows:
                    refundable = float(row["refundable"])
                    self.order_input.addItem(
                        f"{row['invoice_number']} — أمر {row['order_number']} — "
                        f"المتاح للاسترداد {refundable:,.2f}",
                        int(row["id"]),
                    )
                    self.order_input.setItemData(
                        self.order_input.count() - 1,
                        refundable,
                        Qt.UserRole + 1,
                    )
        else:
            partner_type = self._current_partner_type()
            self.order_input.addItem("بدون ربط بفاتورة أو أمر — دفعة مقدمة", None)
            self.order_input.setItemData(0, 0.0, Qt.UserRole + 1)
            if partner_id is not None:
                for order in self.accounting_repository.list_open_orders(
                    partner_type,
                    int(partner_id),
                ):
                    remaining = float(order["remaining"])
                    self.order_input.addItem(
                        f"{order['order_number']} — {order['payment_context']} — "
                        f"المتبقي {remaining:,.2f}",
                        int(order["id"]),
                    )
                    self.order_input.setItemData(
                        self.order_input.count() - 1,
                        remaining,
                        Qt.UserRole + 1,
                    )

        self.order_input.blockSignals(False)
        self._fill_selected_remaining()

    def _fill_selected_remaining(self) -> None:
        if self.order_input.currentData() is None:
            if self._is_refund_mode():
                self.amount_input.clear()
            return
        amount = self.order_input.currentData(Qt.UserRole + 1)
        if amount is not None:
            self.amount_input.setText(f"{float(amount):.2f}")

    def save_payment(self) -> None:
        transaction_type = str(self.transaction_type.currentData())
        if transaction_type not in {"supplier_refund", "customer_refund"}:
            super().save_payment()
            return

        if self.partner_input.currentData() is None:
            party = "المورد" if transaction_type == "supplier_refund" else "العميل"
            QMessageBox.warning(self, "تنبيه", f"اختر {party}")
            return
        if self.order_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر الفاتورة المرتجعة")
            return
        if self.financial_account_input.currentData() is None:
            QMessageBox.warning(
                self,
                "تنبيه",
                "اختر حساب الخزينة أو البنك المستخدم في الحركة",
            )
            return

        try:
            amount = float(self.amount_input.text().strip())
            self.accounting_repository.record_return_refund(
                refund_type=transaction_type,
                partner_id=int(self.partner_input.currentData()),
                invoice_id=int(self.order_input.currentData()),
                amount=amount,
                payment_method=self.method_input.currentText(),
                financial_account_id=int(self.financial_account_input.currentData()),
                notes=self.notes_input.text(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return

        self.amount_input.clear()
        self.notes_input.clear()
        self.reload()
        message = (
            "تم تسجيل استرداد المبلغ من المورد وتحديث رصيد الحساب"
            if transaction_type == "supplier_refund"
            else "تم تسجيل رد المبلغ للعميل وتحديث رصيد الحساب"
        )
        QMessageBox.information(self, "تم", message)

    def _fill_transactions(self) -> None:
        rows = self.accounting_repository.list_transactions()
        self.transactions_table.setRowCount(len(rows))
        labels = {
            "customer_receipt": "تحصيل عميل",
            "supplier_payment": "سداد مورد",
            "supplier_refund": "استرداد من مورد",
            "customer_refund": "رد مبلغ لعميل",
        }
        from PySide6.QtWidgets import QTableWidgetItem

        for row_index, row in enumerate(rows):
            values = [
                row["transaction_number"],
                row["transaction_date"],
                labels.get(row["transaction_type"], row["transaction_type"]),
                row["partner_name"],
                f"{float(row['amount']):,.2f}",
                row["payment_method"],
                row.get("financial_account_name", "-"),
                row.get("reference_number") or "-",
                row.get("notes", ""),
            ]
            for column, value in enumerate(values):
                self.transactions_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(str(value)),
                )


__all__ = ["ReturnRefundAccountsPage"]