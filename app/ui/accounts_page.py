from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
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

from app.models.user import User
from app.repositories.accounting_repository import AccountingRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.partner_repository import PartnerRepository
from app.ui.invoices_tab import InvoicesTab


class AccountsPage(QWidget):
    def __init__(
        self,
        accounting_repository: AccountingRepository,
        partner_repository: PartnerRepository,
        invoice_repository: InvoiceRepository,
        current_user: User | None = None,
    ) -> None:
        super().__init__()
        self.accounting_repository = accounting_repository
        self.partner_repository = partner_repository
        self.invoice_repository = invoice_repository
        self.current_user = current_user
        self.opening_balance_rows: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الحسابات")
        title.setObjectName("titleLabel")
        subtitle = QLabel("متابعة الأرصدة والفواتير والتحصيلات والسداد والمديونيات")
        subtitle.setObjectName("subtitleLabel")

        self.sales_card = self._metric_card("إجمالي فواتير المبيعات")
        self.receipts_card = self._metric_card("تحصيلات العملاء")
        self.customer_advances_card = self._metric_card("دفعات مقدمة من العملاء")
        self.receivables_card = self._metric_card("مديونيات العملاء")
        self.purchases_card = self._metric_card("إجمالي فواتير المشتريات")
        self.payments_card = self._metric_card("مدفوعات الموردين")
        self.supplier_advances_card = self._metric_card("دفعات مقدمة للموردين")
        self.payables_card = self._metric_card("مديونيات الموردين")

        cards = QGridLayout()
        cards.addWidget(self.sales_card[0], 0, 0)
        cards.addWidget(self.receipts_card[0], 0, 1)
        cards.addWidget(self.customer_advances_card[0], 0, 2)
        cards.addWidget(self.receivables_card[0], 0, 3)
        cards.addWidget(self.purchases_card[0], 1, 0)
        cards.addWidget(self.payments_card[0], 1, 1)
        cards.addWidget(self.supplier_advances_card[0], 1, 2)
        cards.addWidget(self.payables_card[0], 1, 3)

        self.customer_table = self._balance_table("العميل")
        self.supplier_table = self._balance_table("المورد")

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        overview_layout.addLayout(cards)

        tabs = QTabWidget()
        tabs.addTab(overview, "الملخص")
        tabs.addTab(self._build_opening_balances_tab(), "الأرصدة الافتتاحية")
        tabs.addTab(self.customer_table, "أرصدة العملاء")
        tabs.addTab(self.supplier_table, "أرصدة الموردين")
        self.sales_invoices_tab = InvoicesTab(invoice_repository, "sales")
        self.purchase_invoices_tab = InvoicesTab(invoice_repository, "purchase")
        tabs.addTab(self.sales_invoices_tab, "فواتير المبيعات")
        tabs.addTab(self.purchase_invoices_tab, "فواتير المشتريات")
        tabs.addTab(self._build_transactions_tab(), "التحصيل والسداد")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(tabs)
        self.reload()

    def _build_opening_balances_tab(self) -> QWidget:
        widget = QWidget()
        self.opening_partner_type_input = QComboBox()
        self.opening_partner_type_input.addItem("عميل", "customer")
        self.opening_partner_type_input.addItem("مورد", "supplier")
        self.opening_partner_type_input.currentIndexChanged.connect(
            self._reload_opening_balance_partners
        )

        self.opening_partner_input = QComboBox()
        self.opening_nature_input = QComboBox()
        self.opening_date_input = QDateEdit()
        self.opening_date_input.setCalendarPopup(True)
        self.opening_date_input.setDisplayFormat("yyyy-MM-dd")
        self.opening_date_input.setDate(QDate.currentDate())
        self.opening_amount_input = QLineEdit()
        self.opening_amount_input.setPlaceholderText("0.00")
        self.opening_notes_input = QLineEdit()
        self.opening_notes_input.setPlaceholderText(
            "مرجع الرصيد أو بيان المراجعة"
        )

        form = QFormLayout()
        form.addRow("نوع الطرف", self.opening_partner_type_input)
        form.addRow("العميل / المورد", self.opening_partner_input)
        form.addRow("طبيعة الرصيد", self.opening_nature_input)
        form.addRow("تاريخ الرصيد", self.opening_date_input)
        form.addRow("المبلغ", self.opening_amount_input)
        form.addRow("ملاحظات", self.opening_notes_input)

        save_button = QPushButton("تسجيل الرصيد الافتتاحي")
        save_button.clicked.connect(self.save_partner_opening_balance)
        reverse_button = QPushButton("عكس القيد المحدد")
        reverse_button.setObjectName("dangerButton")
        reverse_button.clicked.connect(self.reverse_selected_opening_balance)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(reverse_button)
        actions.addWidget(refresh_button)
        actions.addStretch()

        note = QLabel(
            "الرصيد الافتتاحي يؤثر في حساب الطرف والتقارير فقط، "
            "ولا يغيّر رصيد الخزينة أو البنك."
        )
        note.setObjectName("subtitleLabel")

        self.opening_balances_table = QTableWidget(0, 9)
        self.opening_balances_table.setHorizontalHeaderLabels(
            [
                "رقم القيد",
                "التاريخ",
                "النوع",
                "الطرف",
                "طبيعة الرصيد",
                "المبلغ",
                "الحالة",
                "سجله",
                "ملاحظات",
            ]
        )
        self.opening_balances_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.opening_balances_table.setSelectionMode(QTableWidget.SingleSelection)
        self.opening_balances_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.opening_balances_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        self.opening_balances_table.horizontalHeader().setStretchLastSection(True)

        layout = QVBoxLayout(widget)
        layout.addWidget(note)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.opening_balances_table)
        return widget

    def _metric_card(self, title: str) -> tuple[QGroupBox, QLabel]:
        box = QGroupBox(title)
        value = QLabel("0.00")
        value.setAlignment(Qt.AlignCenter)
        value.setStyleSheet("font-size: 24px; font-weight: 900; color: #38BDF8;")
        layout = QVBoxLayout(box)
        layout.addWidget(value)
        return box, value

    def _balance_table(self, partner_label: str) -> QTableWidget:
        table = QTableWidget(0, 6)
        table.setHorizontalHeaderLabels(
            [
                partner_label,
                "الرصيد الافتتاحي",
                "إجمالي الفواتير المعتمدة",
                "المدفوع",
                "دفعات مقدمة",
                "الرصيد المستحق",
            ]
        )
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        return table

    def _build_transactions_tab(self) -> QWidget:
        widget = QWidget()
        self.transaction_type = QComboBox()
        self.transaction_type.addItem("تحصيل من عميل", "customer_receipt")
        self.transaction_type.addItem("سداد لمورد", "supplier_payment")
        self.transaction_type.currentIndexChanged.connect(self._reload_payment_partners)

        self.partner_input = QComboBox()
        self.partner_input.currentIndexChanged.connect(self._reload_open_orders)
        self.order_input = QComboBox()
        self.amount_input = QLineEdit()
        self.amount_input.setPlaceholderText("0.00")
        self.method_input = QComboBox()
        self.method_input.addItems(["نقدي", "تحويل بنكي", "شيك", "محفظة إلكترونية"])
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("ملاحظات اختيارية")

        form = QFormLayout()
        form.addRow("نوع الحركة", self.transaction_type)
        form.addRow("العميل / المورد", self.partner_input)
        form.addRow("ربط بمستند", self.order_input)
        form.addRow("المبلغ", self.amount_input)
        form.addRow("طريقة الدفع", self.method_input)
        form.addRow("ملاحظات", self.notes_input)

        save_button = QPushButton("حفظ الحركة المالية")
        save_button.clicked.connect(self.save_payment)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(refresh_button)
        actions.addStretch()

        self.transactions_table = QTableWidget(0, 8)
        self.transactions_table.setHorizontalHeaderLabels(
            ["رقم الحركة", "التاريخ", "النوع", "الطرف", "المبلغ", "الطريقة", "المستند", "ملاحظات"]
        )
        self.transactions_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.transactions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        layout = QVBoxLayout(widget)
        layout.addLayout(form)
        layout.addLayout(actions)
        layout.addWidget(self.transactions_table)
        return widget

    def reload(self) -> None:
        summary = self.accounting_repository.dashboard_summary()
        self.sales_card[1].setText(f"{float(summary['sales_total']):,.2f}")
        self.receipts_card[1].setText(f"{float(summary['customer_receipts']):,.2f}")
        self.customer_advances_card[1].setText(f"{float(summary['customer_advances']):,.2f}")
        self.receivables_card[1].setText(f"{float(summary['receivables']):,.2f}")
        self.purchases_card[1].setText(f"{float(summary['purchases_total']):,.2f}")
        self.payments_card[1].setText(f"{float(summary['supplier_payments']):,.2f}")
        self.supplier_advances_card[1].setText(f"{float(summary['supplier_advances']):,.2f}")
        self.payables_card[1].setText(f"{float(summary['payables']):,.2f}")
        self._fill_balances(
            self.customer_table,
            self.accounting_repository.list_partner_balances("customer"),
        )
        self._fill_balances(
            self.supplier_table,
            self.accounting_repository.list_partner_balances("supplier"),
        )
        self._reload_opening_balance_partners()
        self._fill_opening_balances()
        self._reload_payment_partners()
        self._fill_transactions()
        self.sales_invoices_tab.reload()
        self.purchase_invoices_tab.reload()

    def _reload_opening_balance_partners(self) -> None:
        if not hasattr(self, "opening_partner_input"):
            return
        partner_type = str(self.opening_partner_type_input.currentData())
        selected_partner = self.opening_partner_input.currentData()
        self.opening_partner_input.blockSignals(True)
        self.opening_partner_input.clear()
        self.opening_partner_input.addItem(
            "اختر العميل" if partner_type == "customer" else "اختر المورد",
            None,
        )
        for partner in self.partner_repository.list_partners(partner_type):
            label = str(partner["name"])
            code = str(partner.get("code") or "").strip()
            if code:
                label = f"{label} — {code}"
            self.opening_partner_input.addItem(label, int(partner["id"]))
        if selected_partner is not None:
            index = self.opening_partner_input.findData(selected_partner)
            if index >= 0:
                self.opening_partner_input.setCurrentIndex(index)
        self.opening_partner_input.blockSignals(False)
        self._reload_opening_balance_natures()

    def _reload_opening_balance_natures(self) -> None:
        selected_nature = self.opening_nature_input.currentData()
        partner_type = str(self.opening_partner_type_input.currentData())
        self.opening_nature_input.clear()
        if partner_type == "customer":
            self.opening_nature_input.addItem(
                "رصيد مدين – مبلغ مستحق على العميل",
                "debit",
            )
            self.opening_nature_input.addItem(
                "رصيد دائن – دفعة مقدمة من العميل",
                "credit",
            )
        else:
            self.opening_nature_input.addItem(
                "رصيد دائن – مبلغ مستحق للمورد",
                "credit",
            )
            self.opening_nature_input.addItem(
                "رصيد مدين – دفعة مقدمة للمورد",
                "debit",
            )
        if selected_nature is not None:
            index = self.opening_nature_input.findData(selected_nature)
            if index >= 0:
                self.opening_nature_input.setCurrentIndex(index)

    def save_partner_opening_balance(self) -> None:
        if self.current_user is None:
            QMessageBox.warning(self, "تنبيه", "تعذر تحديد المستخدم الحالي")
            return
        if self.opening_partner_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل أو المورد")
            return
        try:
            amount = float(self.opening_amount_input.text().strip())
            selected_date = self.opening_date_input.date()
            self.accounting_repository.record_partner_opening_balance(
                partner_type=str(self.opening_partner_type_input.currentData()),
                partner_id=int(self.opening_partner_input.currentData()),
                nature=str(self.opening_nature_input.currentData()),
                amount=amount,
                entry_date=selected_date.toString("yyyy-MM-dd"),
                notes=self.opening_notes_input.text(),
                created_by_user_id=int(self.current_user.id),
            )
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.opening_amount_input.clear()
        self.opening_notes_input.clear()
        self.reload()
        QMessageBox.information(
            self,
            "تم",
            "تم تسجيل الرصيد الافتتاحي وتحديث حساب الطرف والتقارير.",
        )

    def reverse_selected_opening_balance(self) -> None:
        if self.current_user is None:
            QMessageBox.warning(self, "تنبيه", "تعذر تحديد المستخدم الحالي")
            return
        row_index = self.opening_balances_table.currentRow()
        if row_index < 0 or row_index >= len(self.opening_balance_rows):
            QMessageBox.warning(self, "تنبيه", "اختر قيدًا من الجدول")
            return
        reason, accepted = QInputDialog.getText(
            self,
            "عكس الرصيد الافتتاحي",
            "اكتب سبب عكس القيد:",
        )
        if not accepted:
            return
        try:
            self.accounting_repository.reverse_partner_opening_balance(
                int(self.opening_balance_rows[row_index]["id"]),
                reason=reason,
                created_by_user_id=int(self.current_user.id),
            )
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(
            self,
            "تم",
            "تم إنشاء قيد عكسي وإلغاء أثر الرصيد الافتتاحي المحدد.",
        )

    def _fill_opening_balances(self) -> None:
        self.opening_balance_rows = (
            self.accounting_repository.list_partner_opening_balance_entries()
        )
        self.opening_balances_table.setRowCount(len(self.opening_balance_rows))
        type_labels = {"customer": "عميل", "supplier": "مورد"}
        status_labels = {
            "posted": "معتمد",
            "reversed": "تم عكسه",
            "reversal": "قيد عكسي",
        }
        for row_index, row in enumerate(self.opening_balance_rows):
            if str(row["partner_type"]) == "customer":
                nature_label = (
                    "رصيد مدين – مبلغ مستحق على العميل"
                    if str(row["nature"]) == "debit"
                    else "رصيد دائن – دفعة مقدمة من العميل"
                )
            else:
                nature_label = (
                    "رصيد دائن – مبلغ مستحق للمورد"
                    if str(row["nature"]) == "credit"
                    else "رصيد مدين – دفعة مقدمة للمورد"
                )
            values = [
                row["entry_number"],
                row["entry_date"],
                type_labels.get(str(row["partner_type"]), row["partner_type"]),
                row["partner_name"],
                nature_label,
                f"{float(row['amount']):,.2f}",
                status_labels.get(str(row["status"]), row["status"]),
                row["created_by_name"] or "-",
                row["notes"],
            ]
            for column, value in enumerate(values):
                self.opening_balances_table.setItem(
                    row_index,
                    column,
                    QTableWidgetItem(str(value)),
                )

    def _fill_balances(self, table: QTableWidget, rows: list[dict]) -> None:
        table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["name"],
                f"{float(row['opening_balance']):,.2f}",
                f"{float(row['invoices_total']):,.2f}",
                f"{float(row['paid']):,.2f}",
                f"{float(row['advances']):,.2f}",
                f"{float(row['balance']):,.2f}",
            ]
            for column, value in enumerate(values):
                table.setItem(row_index, column, QTableWidgetItem(str(value)))

    def _reload_payment_partners(self) -> None:
        partner_type = (
            "customer" if self.transaction_type.currentData() == "customer_receipt" else "supplier"
        )
        selected = self.partner_input.currentData()
        self.partner_input.blockSignals(True)
        self.partner_input.clear()
        for partner in self.partner_repository.list_partners(partner_type):
            self.partner_input.addItem(partner["name"], partner["id"])
        if selected is not None:
            index = self.partner_input.findData(selected)
            if index >= 0:
                self.partner_input.setCurrentIndex(index)
        self.partner_input.blockSignals(False)
        self._reload_open_orders()

    def _reload_open_orders(self) -> None:
        partner_id = self.partner_input.currentData()
        partner_type = (
            "customer" if self.transaction_type.currentData() == "customer_receipt" else "supplier"
        )
        self.order_input.clear()
        self.order_input.addItem("بدون ربط بمستند محدد", None)
        if partner_id is None:
            return
        for order in self.accounting_repository.list_open_orders(partner_type, int(partner_id)):
            self.order_input.addItem(
                f"{order['order_number']} — {order['payment_context']} — "
                f"المتبقي {float(order['remaining']):,.2f}",
                order["id"],
            )

    def save_payment(self) -> None:
        if self.partner_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل أو المورد")
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
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.amount_input.clear()
        self.notes_input.clear()
        self.reload()
        QMessageBox.information(self, "تم", "تم حفظ الحركة المالية وتحديث الأرصدة")

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
                row["reference_number"] or "-",
                row["notes"],
            ]
            for column, value in enumerate(values):
                self.transactions_table.setItem(row_index, column, QTableWidgetItem(str(value)))
