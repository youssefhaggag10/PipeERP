from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTabWidget,
)

from app.services.payment_account_rules import allowed_account_types
from app.ui.treasury_accounts_page import ACCOUNT_TYPES, TreasuryAccountsPage


class StrictTreasuryAccountsPage(TreasuryAccountsPage):
    """Central receipts/payments screen plus simple treasury account maintenance."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._account_rows: list[dict] = []
        self._hide_transfer_section()
        self._add_account_management_actions()
        self.method_input.currentIndexChanged.connect(self._filter_payment_accounts)
        self.order_input.currentIndexChanged.connect(self._fill_selected_remaining)
        self.transaction_type.currentIndexChanged.connect(self._refresh_payment_form)
        self._refresh_payment_form()

    def _hide_transfer_section(self) -> None:
        for group in self.findChildren(QGroupBox):
            if group.title().strip() == "تحويل بين الخزائن والبنوك":
                group.hide()

    def _add_account_management_actions(self) -> None:
        tabs = self.findChild(QTabWidget)
        if tabs is None or tabs.count() == 0:
            return
        treasury_widget = tabs.widget(tabs.count() - 1)
        if treasury_widget is None or treasury_widget.layout() is None:
            return

        edit_button = QPushButton("تعديل الحساب المحدد")
        edit_button.setObjectName("secondaryButton")
        edit_button.clicked.connect(self.edit_selected_financial_account)

        adjust_button = QPushButton("تسوية رصيد الحساب المحدد")
        adjust_button.clicked.connect(self.adjust_selected_financial_account)

        actions = QHBoxLayout()
        actions.addWidget(edit_button)
        actions.addWidget(adjust_button)
        actions.addStretch()
        treasury_widget.layout().insertLayout(3, actions)

    def reload(self) -> None:
        super().reload()
        if hasattr(self, "partner_input"):
            self._refresh_payment_form()

    def _refresh_payment_form(self) -> None:
        self._reload_payment_partners()
        self._filter_payment_accounts()

    def _reload_payment_partners(self) -> None:
        is_customer = self.transaction_type.currentData() == "customer_receipt"
        partner_type = "customer" if is_customer else "supplier"
        placeholder = "اختر العميل" if is_customer else "اختر المورد"
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
        partner_type = (
            "customer"
            if self.transaction_type.currentData() == "customer_receipt"
            else "supplier"
        )
        self.order_input.blockSignals(True)
        self.order_input.clear()
        self.order_input.addItem("بدون ربط بفاتورة أو أمر — دفعة مقدمة", None)
        self.order_input.setItemData(0, 0.0, Qt.UserRole + 1)
        if partner_id is not None:
            for order in self.accounting_repository.list_open_orders(
                partner_type, int(partner_id)
            ):
                remaining = float(order["remaining"])
                label = (
                    f"{order['order_number']} — {order['payment_context']} — "
                    f"المتبقي {remaining:,.2f}"
                )
                self.order_input.addItem(label, int(order["id"]))
                self.order_input.setItemData(
                    self.order_input.count() - 1, remaining, Qt.UserRole + 1
                )
        self.order_input.blockSignals(False)
        self._fill_selected_remaining()

    def _fill_selected_remaining(self) -> None:
        if self.order_input.currentData() is None:
            return
        remaining = self.order_input.currentData(Qt.UserRole + 1)
        if remaining is not None:
            self.amount_input.setText(f"{float(remaining):.2f}")

    def _reload_financial_accounts(self) -> None:
        self._filter_payment_accounts()

    def _filter_payment_accounts(self) -> None:
        if not hasattr(self, "financial_account_input"):
            return
        selected = self.financial_account_input.currentData()
        allowed = allowed_account_types(self.method_input.currentText())
        accounts = [
            account
            for account in self.accounting_repository.list_financial_accounts()
            if str(account["account_type"]) in allowed
        ]
        self.financial_account_input.blockSignals(True)
        self.financial_account_input.clear()
        self.financial_account_input.addItem("اختر الحساب المالي", None)
        for account in accounts:
            self.financial_account_input.addItem(
                f"{account['name']} — رصيد {float(account['current_balance']):,.2f}",
                int(account["id"]),
            )
        if selected is not None:
            index = self.financial_account_input.findData(selected)
            if index >= 0:
                self.financial_account_input.setCurrentIndex(index)
        self.financial_account_input.blockSignals(False)

    def _fill_financial_accounts(self) -> None:
        self._account_rows = self.accounting_repository.list_financial_accounts()
        self.accounts_table.setRowCount(len(self._account_rows))
        for row_index, row in enumerate(self._account_rows):
            values = [
                row["code"],
                row["name"],
                ACCOUNT_TYPES.get(str(row["account_type"]), str(row["account_type"])),
                f"{float(row['opening_balance']):,.2f}",
                f"{float(row['current_balance']):,.2f}",
                "نعم" if bool(row["is_default"]) else "لا",
                row["notes"],
            ]
            from PySide6.QtWidgets import QTableWidgetItem
            for column, value in enumerate(values):
                self.accounts_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _selected_account(self) -> dict | None:
        row_index = self.accounts_table.currentRow()
        if row_index < 0 or row_index >= len(self._account_rows):
            QMessageBox.warning(self, "تنبيه", "اختر حسابًا من جدول الخزائن والبنوك")
            return None
        return self._account_rows[row_index]

    def edit_selected_financial_account(self) -> None:
        account = self._selected_account()
        if account is None:
            return

        code, accepted = QInputDialog.getText(
            self, "تعديل الحساب", "كود الحساب:", text=str(account["code"])
        )
        if not accepted:
            return
        name, accepted = QInputDialog.getText(
            self, "تعديل الحساب", "اسم الحساب:", text=str(account["name"])
        )
        if not accepted:
            return

        type_codes = list(ACCOUNT_TYPES.keys())
        type_labels = [ACCOUNT_TYPES[code] for code in type_codes]
        current_index = type_codes.index(str(account["account_type"]))
        type_label, accepted = QInputDialog.getItem(
            self,
            "تعديل الحساب",
            "نوع الحساب:",
            type_labels,
            current_index,
            False,
        )
        if not accepted:
            return
        account_type = type_codes[type_labels.index(type_label)]

        notes, accepted = QInputDialog.getText(
            self, "تعديل الحساب", "ملاحظات:", text=str(account["notes"] or "")
        )
        if not accepted:
            return

        try:
            self.accounting_repository.update_financial_account(
                int(account["id"]),
                code=code,
                name=name,
                account_type=account_type,
                notes=notes,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم تعديل بيانات الحساب المالي")

    def adjust_selected_financial_account(self) -> None:
        account = self._selected_account()
        if account is None:
            return
        current_balance = float(account["current_balance"])
        target_balance, accepted = QInputDialog.getDouble(
            self,
            "تسوية رصيد الحساب",
            f"الرصيد الدفتري الحالي: {current_balance:,.2f}\nأدخل الرصيد الفعلي الجديد:",
            value=current_balance,
            minValue=-999999999999.99,
            maxValue=999999999999.99,
            decimals=2,
        )
        if not accepted:
            return
        reason, accepted = QInputDialog.getText(
            self,
            "سبب التسوية",
            "اكتب سبب التسوية أو مرجع كشف الحساب:",
        )
        if not accepted:
            return
        try:
            self.accounting_repository.adjust_financial_account_balance(
                int(account["id"]),
                target_balance=float(target_balance),
                notes=reason,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(
            self,
            "تم",
            f"تمت تسوية رصيد {account['name']} إلى {target_balance:,.2f}",
        )

    def save_payment(self) -> None:
        if self.partner_input.currentData() is None:
            party = "العميل" if self.transaction_type.currentData() == "customer_receipt" else "المورد"
            QMessageBox.warning(self, "تنبيه", f"اختر {party}")
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
            self.accounting_repository.record_payment(
                transaction_type=str(self.transaction_type.currentData()),
                partner_id=int(self.partner_input.currentData()),
                amount=amount,
                payment_method=self.method_input.currentText(),
                reference_id=self.order_input.currentData(),
                notes=self.notes_input.text(),
                financial_account_id=int(self.financial_account_input.currentData()),
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
            "تم حفظ الحركة على الحساب المالي المحدد وتحديث رصيد المستند",
        )


__all__ = ["StrictTreasuryAccountsPage"]
