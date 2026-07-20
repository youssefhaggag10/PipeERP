from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
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
    ) -> None:
        super().__init__()
        self.accounting_repository = accounting_repository
        self.partner_repository = partner_repository
        self.invoice_repository = invoice_repository
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
        self._reload_payment_partners()
        self._fill_transactions()
        self.sales_invoices_tab.reload()
        self.purchase_invoices_tab.reload()

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
