from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.print_enabled_pages import AccountsPageWithPrint

ACCOUNT_TYPES = {
    "cash": "خزينة نقدية",
    "bank": "حساب بنكي",
    "wallet": "محفظة إلكترونية",
    "other": "حساب دفع آخر",
}


class TreasuryAccountsPage(AccountsPageWithPrint):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._add_payment_account_selector()
        self._add_treasury_tab()
        self._expand_transaction_table()
        self.reload()

    def _add_payment_account_selector(self) -> None:
        self.financial_account_input = QComboBox()
        transaction_widget = self.transactions_table.parentWidget()
        if transaction_widget is None or transaction_widget.layout() is None:
            return
        row = QHBoxLayout()
        label = QLabel("حساب الخزينة / البنك")
        row.addWidget(label)
        row.addWidget(self.financial_account_input, 1)
        transaction_widget.layout().insertLayout(1, row)

    def _add_treasury_tab(self) -> None:
        tabs = self.findChild(QTabWidget)
        if tabs is None:
            return
        treasury_widget = QWidget()
        layout = QVBoxLayout(treasury_widget)

        accounts_group = QGroupBox("تعريف خزينة أو حساب بنكي")
        accounts_form = QFormLayout(accounts_group)
        self.account_code_input = QLineEdit()
        self.account_code_input.setPlaceholderText("مثال: BANK-NBE أو CASH-02")
        self.account_name_input = QLineEdit()
        self.account_name_input.setPlaceholderText("اسم الخزينة أو البنك")
        self.account_type_input = QComboBox()
        for code, label in ACCOUNT_TYPES.items():
            self.account_type_input.addItem(label, code)
        self.opening_balance_input = QLineEdit("0")
        self.opening_balance_input.setPlaceholderText("0.00")
        self.default_account_check = QCheckBox("اجعله الحساب الافتراضي")
        self.account_notes_input = QLineEdit()
        self.account_notes_input.setPlaceholderText("ملاحظات اختيارية")
        create_button = QPushButton("إضافة الحساب المالي")
        create_button.clicked.connect(self.create_financial_account)
        accounts_form.addRow("الكود", self.account_code_input)
        accounts_form.addRow("الاسم", self.account_name_input)
        accounts_form.addRow("النوع", self.account_type_input)
        accounts_form.addRow("الرصيد الافتتاحي", self.opening_balance_input)
        accounts_form.addRow("الافتراضي", self.default_account_check)
        accounts_form.addRow("ملاحظات", self.account_notes_input)
        accounts_form.addRow(create_button)

        self.accounts_table = QTableWidget(0, 7)
        self.accounts_table.setHorizontalHeaderLabels(
            ["الكود", "الحساب", "النوع", "رصيد افتتاحي", "الرصيد الحالي", "افتراضي", "ملاحظات"]
        )
        self.accounts_table.setEditTriggers(QTableWidget.NoEditTriggers)
        default_button = QPushButton("تعيين الحساب المحدد كافتراضي")
        default_button.clicked.connect(self.set_selected_default_account)

        transfer_group = QGroupBox("تحويل بين الخزائن والبنوك")
        transfer_form = QFormLayout(transfer_group)
        self.transfer_from_input = QComboBox()
        self.transfer_to_input = QComboBox()
        self.transfer_amount_input = QLineEdit()
        self.transfer_amount_input.setPlaceholderText("0.00")
        self.transfer_notes_input = QLineEdit()
        self.transfer_notes_input.setPlaceholderText("سبب أو بيان التحويل")
        transfer_button = QPushButton("تنفيذ التحويل")
        transfer_button.clicked.connect(self.transfer_between_accounts)
        transfer_form.addRow("من حساب", self.transfer_from_input)
        transfer_form.addRow("إلى حساب", self.transfer_to_input)
        transfer_form.addRow("المبلغ", self.transfer_amount_input)
        transfer_form.addRow("البيان", self.transfer_notes_input)
        transfer_form.addRow(transfer_button)

        self.movements_table = QTableWidget(0, 8)
        self.movements_table.setHorizontalHeaderLabels(
            [
                "التاريخ",
                "رقم الحركة",
                "الحساب",
                "نوع الحركة",
                "داخل",
                "خارج",
                "الطرف / الحساب المقابل",
                "البيان",
            ]
        )
        self.movements_table.setEditTriggers(QTableWidget.NoEditTriggers)

        layout.addWidget(accounts_group)
        layout.addWidget(self.accounts_table)
        layout.addWidget(default_button)
        layout.addWidget(transfer_group)
        layout.addWidget(QLabel("كشف حركة الخزائن والبنوك"))
        layout.addWidget(self.movements_table)
        tabs.addTab(treasury_widget, "الخزينة والبنوك")

    def _expand_transaction_table(self) -> None:
        self.transactions_table.setColumnCount(9)
        self.transactions_table.setHorizontalHeaderLabels(
            [
                "رقم الحركة",
                "التاريخ",
                "النوع",
                "الطرف",
                "المبلغ",
                "الطريقة",
                "الحساب",
                "المستند",
                "ملاحظات",
            ]
        )

    def reload(self) -> None:
        super().reload()
        if hasattr(self, "financial_account_input"):
            self._reload_financial_accounts()
        if hasattr(self, "accounts_table"):
            self._fill_financial_accounts()
            self._fill_account_movements()

    def _reload_financial_accounts(self) -> None:
        accounts = self.accounting_repository.list_financial_accounts()
        controls = [
            self.financial_account_input,
            getattr(self, "transfer_from_input", None),
            getattr(self, "transfer_to_input", None),
        ]
        for control in controls:
            if control is None:
                continue
            selected = control.currentData()
            control.blockSignals(True)
            control.clear()
            for account in accounts:
                label = f"{account['name']} — رصيد {float(account['current_balance']):,.2f}"
                control.addItem(label, account["id"])
                if bool(account["is_default"]):
                    control.setItemData(control.count() - 1, "الحساب الافتراضي", Qt.ToolTipRole)
            if selected is not None:
                index = control.findData(selected)
                if index >= 0:
                    control.setCurrentIndex(index)
            elif control is self.financial_account_input:
                for index, account in enumerate(accounts):
                    if bool(account["is_default"]):
                        control.setCurrentIndex(index)
                        break
            control.blockSignals(False)

    def save_payment(self) -> None:
        if self.partner_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل أو المورد")
            return
        if self.financial_account_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر حساب الخزينة أو البنك")
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
        QMessageBox.information(self, "تم", "تم حفظ الحركة على حساب الخزينة أو البنك المحدد")

    def create_financial_account(self) -> None:
        try:
            opening_balance = float(self.opening_balance_input.text().strip() or 0)
            self.accounting_repository.create_financial_account(
                code=self.account_code_input.text(),
                name=self.account_name_input.text(),
                account_type=str(self.account_type_input.currentData()),
                opening_balance=opening_balance,
                is_default=self.default_account_check.isChecked(),
                notes=self.account_notes_input.text(),
            )
        except (ValueError, Exception) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.account_code_input.clear()
        self.account_name_input.clear()
        self.opening_balance_input.setText("0")
        self.default_account_check.setChecked(False)
        self.account_notes_input.clear()
        self.reload()
        QMessageBox.information(self, "تم", "تمت إضافة الحساب المالي")

    def set_selected_default_account(self) -> None:
        row_index = self.accounts_table.currentRow()
        rows = self.accounting_repository.list_financial_accounts()
        if row_index < 0 or row_index >= len(rows):
            QMessageBox.warning(self, "تنبيه", "اختر حسابًا من الجدول")
            return
        try:
            self.accounting_repository.set_default_financial_account(int(rows[row_index]["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()

    def transfer_between_accounts(self) -> None:
        if (
            self.transfer_from_input.currentData() is None
            or self.transfer_to_input.currentData() is None
        ):
            QMessageBox.warning(self, "تنبيه", "اختر الحساب المحول منه والحساب المحول إليه")
            return
        try:
            self.accounting_repository.transfer_between_accounts(
                from_account_id=int(self.transfer_from_input.currentData()),
                to_account_id=int(self.transfer_to_input.currentData()),
                amount=float(self.transfer_amount_input.text().strip()),
                notes=self.transfer_notes_input.text(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.transfer_amount_input.clear()
        self.transfer_notes_input.clear()
        self.reload()
        QMessageBox.information(self, "تم", "تم التحويل بين الحسابات وتحديث الأرصدة")

    def _fill_financial_accounts(self) -> None:
        rows = self.accounting_repository.list_financial_accounts()
        self.accounts_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["code"],
                row["name"],
                ACCOUNT_TYPES.get(str(row["account_type"]), str(row["account_type"])),
                f"{float(row['opening_balance']):,.2f}",
                f"{float(row['current_balance']):,.2f}",
                "نعم" if bool(row["is_default"]) else "لا",
                row["notes"],
            ]
            for column, value in enumerate(values):
                self.accounts_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _fill_account_movements(self) -> None:
        rows = self.accounting_repository.list_account_movements()
        self.movements_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["movement_date"],
                row["movement_number"],
                row["account_name"],
                row["movement_type"],
                f"{float(row['amount_in']):,.2f}",
                f"{float(row['amount_out']):,.2f}",
                row["counterparty"],
                row["notes"],
            ]
            for column, value in enumerate(values):
                self.movements_table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _fill_transactions(self) -> None:
        rows = self.accounting_repository.list_transactions()
        self.transactions_table.setRowCount(len(rows))
        labels = {"customer_receipt": "تحصيل عميل", "supplier_payment": "سداد مورد"}
        for row_index, row in enumerate(rows):
            values = [
                row["transaction_number"],
                row["transaction_date"],
                labels.get(row["transaction_type"], row["transaction_type"]),
                row["partner_name"],
                f"{float(row['amount']):,.2f}",
                row["payment_method"],
                row.get("financial_account_name", "-"),
                row["reference_number"] or "-",
                row["notes"],
            ]
            for column, value in enumerate(values):
                self.transactions_table.setItem(row_index, column, QTableWidgetItem(str(value)))


__all__ = ["TreasuryAccountsPage"]
