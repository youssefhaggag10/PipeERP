from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.repositories.invoice_repository import InvoiceRepository
from app.services.invoice_service import INVOICE_STATUS_LABELS, PAYMENT_STATUS_LABELS
from app.utils.datetime_utils import format_egypt_datetime


INVOICE_COLORS = {
    "draft": QColor("#64748B"),
    "posted": QColor("#2563EB"),
    "cancelled": QColor("#DC2626"),
}

PAYMENT_COLORS = {
    "unpaid": QColor("#DC2626"),
    "partial": QColor("#D97706"),
    "paid": QColor("#16A34A"),
    "cancelled": QColor("#64748B"),
}


class InvoicesTab(QWidget):
    def __init__(self, repository: InvoiceRepository, invoice_type: str) -> None:
        super().__init__()
        self.repository = repository
        self.invoice_type = invoice_type
        self.rows: list[dict] = []
        self.setLayoutDirection(Qt.RightToLeft)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "بحث برقم الفاتورة أو رقم الأمر أو الاسم أو رقم الهاتف"
        )
        self.search_input.textChanged.connect(self._apply_search)

        self.table = QTableWidget(0, 10)
        partner_label = "العميل" if invoice_type == "sales" else "المورد"
        self.table.setHorizontalHeaderLabels(
            [
                "رقم الفاتورة",
                "رقم الأمر",
                "الوقت",
                partner_label,
                "الهاتف",
                "الإجمالي",
                "المدفوع",
                "المتبقي",
                "حالة الفاتورة",
                "حالة الدفع",
            ]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        post_button = QPushButton("اعتماد الفاتورة")
        post_button.clicked.connect(self.post_selected)
        payment_button = QPushButton(
            "تسجيل تحصيل" if invoice_type == "sales" else "تسجيل سداد"
        )
        payment_button.clicked.connect(self.pay_selected)
        cancel_button = QPushButton("إلغاء الفاتورة")
        cancel_button.setObjectName("dangerButton")
        cancel_button.clicked.connect(self.cancel_selected)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)

        actions = QHBoxLayout()
        actions.addWidget(post_button)
        actions.addWidget(payment_button)
        actions.addWidget(cancel_button)
        actions.addWidget(refresh_button)
        actions.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_input)
        layout.addLayout(actions)
        layout.addWidget(self.table)
        self.reload()

    def reload(self) -> None:
        try:
            self.rows = self.repository.list_invoices(self.invoice_type)
        except Exception as error:
            QMessageBox.critical(self, "خطأ", f"تعذر تحميل الفواتير: {error}")
            return

        for row in self.rows:
            if self.invoice_type == "sales":
                phone_row = self.repository.database.fetch_one(
                    """
                    SELECT COALESCE(p.phone, '') AS phone
                    FROM sales_invoices si
                    JOIN partners p ON p.id = si.customer_id
                    WHERE si.id = ?
                    """,
                    (int(row["id"]),),
                )
            else:
                phone_row = self.repository.database.fetch_one(
                    """
                    SELECT COALESCE(p.phone, '') AS phone
                    FROM purchase_invoices pi
                    JOIN partners p ON p.id = pi.supplier_id
                    WHERE pi.id = ?
                    """,
                    (int(row["id"]),),
                )
            row["partner_phone"] = "" if phone_row is None else str(phone_row["phone"] or "")

        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            values = [
                row["invoice_number"],
                row["order_number"],
                format_egypt_datetime(row["invoice_date"]),
                row["partner_name"],
                row["partner_phone"],
                f"{float(row['total']):,.2f}",
                f"{float(row['paid']):,.2f}",
                f"{float(row['remaining']):,.2f}",
                INVOICE_STATUS_LABELS.get(str(row["status"]), str(row["status"])),
                PAYMENT_STATUS_LABELS.get(
                    str(row["payment_status"]), str(row["payment_status"])
                ),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                if column_index == 8:
                    item.setBackground(INVOICE_COLORS.get(str(row["status"]), QColor("#64748B")))
                    item.setForeground(QColor("white"))
                elif column_index == 9:
                    item.setBackground(
                        PAYMENT_COLORS.get(str(row["payment_status"]), QColor("#64748B"))
                    )
                    item.setForeground(QColor("white"))
                self.table.setItem(row_index, column_index, item)
        self._apply_search()

    def _apply_search(self) -> None:
        query = self.search_input.text().strip().casefold()
        for row_index, row in enumerate(self.rows):
            haystack = " ".join(
                str(row.get(key, ""))
                for key in (
                    "invoice_number",
                    "order_number",
                    "partner_name",
                    "partner_phone",
                )
            ).casefold()
            self.table.setRowHidden(row_index, bool(query) and query not in haystack)

    def _selected(self) -> dict | None:
        row_index = self.table.currentRow()
        if row_index < 0 or row_index >= len(self.rows):
            QMessageBox.warning(self, "تنبيه", "اختر فاتورة من الجدول")
            return None
        return self.rows[row_index]

    def post_selected(self) -> None:
        row = self._selected()
        if row is None:
            return
        try:
            self.repository.post_invoice(self.invoice_type, int(row["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم اعتماد الفاتورة")

    def cancel_selected(self) -> None:
        row = self._selected()
        if row is None:
            return
        answer = QMessageBox.question(
            self,
            "تأكيد الإلغاء",
            "سيتم إلغاء الفاتورة مع الاحتفاظ برقمها وسجلها. هل تريد المتابعة؟",
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.repository.cancel_invoice(self.invoice_type, int(row["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم إلغاء الفاتورة")

    def pay_selected(self) -> None:
        row = self._selected()
        if row is None:
            return
        remaining = float(row["remaining"])
        if remaining <= 0.000001:
            QMessageBox.information(self, "تنبيه", "الفاتورة مدفوعة بالكامل")
            return
        amount, accepted = QInputDialog.getDouble(
            self,
            "تسجيل دفعة",
            f"المتبقي على الفاتورة: {remaining:,.2f}\nأدخل المبلغ:",
            value=remaining,
            minValue=0.01,
            maxValue=remaining,
            decimals=2,
        )
        if not accepted:
            return
        methods = ["نقدي", "تحويل بنكي", "شيك", "محفظة إلكترونية"]
        method, accepted = QInputDialog.getItem(
            self, "طريقة الدفع", "اختر طريقة الدفع:", methods, 0, False
        )
        if not accepted:
            return
        try:
            self.repository.record_invoice_payment(
                invoice_type=self.invoice_type,
                invoice_id=int(row["id"]),
                amount=float(amount),
                payment_method=str(method),
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم تسجيل الحركة المالية وتحديث حالة الدفع")
