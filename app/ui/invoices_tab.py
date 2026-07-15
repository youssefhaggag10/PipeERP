from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
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
from app.ui.invoice_return_dialog import InvoiceReturnDialog
from app.ui.payment_account_selector import (
    choose_financial_account,
    choose_payment_method,
)
from app.utils.datetime_utils import format_egypt_datetime

INVOICE_COLORS = {
    "draft": QColor("#64748B"),
    "posted": QColor("#2563EB"),
    "cancelled": QColor("#DC2626"),
}

RETURN_COLORS = {
    "مستلمة": QColor("#2563EB"),
    "مُسلَّمة": QColor("#2563EB"),
    "مرتجع جزئي": QColor("#D97706"),
    "مرتجع كلي": QColor("#DC2626"),
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
            "بحث برقم الفاتورة أو رقم الأمر أو الاسم أو رقم الهاتف أو طريقة الدفع"
        )
        self.search_input.textChanged.connect(self._apply_search)

        self.table = QTableWidget(0, 14)
        partner_label = "العميل" if invoice_type == "sales" else "المورد"
        self.table.setHorizontalHeaderLabels(
            [
                "رقم الفاتورة",
                "رقم الأمر",
                "الوقت",
                partner_label,
                "الهاتف",
                "الإجمالي الأصلي",
                "المرتجع",
                "صافي الفاتورة",
                "المدفوع",
                "طريقة الدفع",
                "المتبقي",
                "حالة الفاتورة",
                "حالة التسليم / المرتجع",
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
        return_button = QPushButton("إنشاء مرتجع")
        return_button.clicked.connect(self.return_selected)
        cancel_button = QPushButton("إلغاء الفاتورة")
        cancel_button.setObjectName("dangerButton")
        cancel_button.clicked.connect(self.cancel_selected)
        refresh_button = QPushButton("تحديث")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self.reload)

        actions = QHBoxLayout()
        actions.addWidget(post_button)
        actions.addWidget(payment_button)
        actions.addWidget(return_button)
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
                details_row = self.repository.database.fetch_one(
                    """
                    SELECT COALESCE(p.phone, '') AS phone,
                           COALESCE((
                               SELECT GROUP_CONCAT(DISTINCT NULLIF(TRIM(pt.payment_method), ''))
                               FROM payment_transactions pt
                               WHERE pt.sales_invoice_id = si.id
                           ), '') AS payment_methods
                    FROM sales_invoices si
                    JOIN partners p ON p.id = si.customer_id
                    WHERE si.id = ?
                    """,
                    (int(row["id"]),),
                )
            else:
                details_row = self.repository.database.fetch_one(
                    """
                    SELECT COALESCE(p.phone, '') AS phone,
                           COALESCE((
                               SELECT GROUP_CONCAT(DISTINCT NULLIF(TRIM(pt.payment_method), ''))
                               FROM payment_transactions pt
                               WHERE pt.purchase_invoice_id = pi.id
                           ), '') AS payment_methods
                    FROM purchase_invoices pi
                    JOIN partners p ON p.id = pi.supplier_id
                    WHERE pi.id = ?
                    """,
                    (int(row["id"]),),
                )
            row["partner_phone"] = "" if details_row is None else str(details_row["phone"] or "")
            raw_methods = "" if details_row is None else str(details_row["payment_methods"] or "")
            methods = [method.strip() for method in raw_methods.split(",") if method.strip()]
            row["payment_methods"] = (
                "، ".join(methods)
                if methods
                else ("غير محددة" if float(row["paid"]) > 0.000001 else "—")
            )
            row.setdefault("returned_total", 0.0)
            row.setdefault("net_total", float(row["total"]))
            row.setdefault(
                "return_status",
                "مُسلَّمة" if self.invoice_type == "sales" else "مستلمة",
            )

        self.table.setRowCount(len(self.rows))
        for row_index, row in enumerate(self.rows):
            values = [
                row["invoice_number"],
                row["order_number"],
                format_egypt_datetime(row["invoice_date"]),
                row["partner_name"],
                row["partner_phone"],
                f"{float(row['total']):,.2f}",
                f"{float(row['returned_total']):,.2f}",
                f"{float(row['net_total']):,.2f}",
                f"{float(row['paid']):,.2f}",
                row["payment_methods"],
                f"{float(row['remaining']):,.2f}",
                INVOICE_STATUS_LABELS.get(str(row["status"]), str(row["status"])),
                row["return_status"],
                PAYMENT_STATUS_LABELS.get(
                    str(row["payment_status"]), str(row["payment_status"])
                ),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)
                if column_index == 11:
                    item.setBackground(INVOICE_COLORS.get(str(row["status"]), QColor("#64748B")))
                    item.setForeground(QColor("white"))
                elif column_index == 12:
                    item.setBackground(RETURN_COLORS.get(str(row["return_status"]), QColor("#64748B")))
                    item.setForeground(QColor("white"))
                elif column_index == 13:
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
                    "payment_methods",
                    "return_status",
                )
            ).casefold()
            self.table.setRowHidden(row_index, bool(query) and query not in haystack)

    def _selected(self) -> dict | None:
        row_index = self.table.currentRow()
        if row_index < 0 or row_index >= len(self.rows):
            QMessageBox.warning(self, "تنبيه", "اختر فاتورة من الجدول")
            return None
        return self.rows[row_index]

    def return_selected(self) -> None:
        row = self._selected()
        if row is None:
            return
        if str(row["status"]) != "posted":
            QMessageBox.warning(self, "تنبيه", "يمكن عمل مرتجع لفاتورة معتمدة فقط")
            return
        if not hasattr(self.repository, "get_returnable_lines"):
            QMessageBox.warning(self, "تنبيه", "ميزة المرتجعات غير مفعلة")
            return
        try:
            lines = self.repository.get_returnable_lines(self.invoice_type, int(row["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        if not any(float(line["remaining_quantity"]) > 0.000001 for line in lines):
            QMessageBox.information(self, "تنبيه", "تم إرجاع جميع بنود الفاتورة بالكامل")
            return
        dialog = InvoiceReturnDialog(lines, self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.repository.create_return(
                invoice_type=self.invoice_type,
                invoice_id=int(row["id"]),
                quantities=dialog.quantities(),
                reason=dialog.reason(),
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم إنشاء مستند المرتجع وتحديث المخزون وصافي الفاتورة")

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
            QMessageBox.information(self, "تنبيه", "لا يوجد مبلغ متبقٍ على الفاتورة")
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
        method = choose_payment_method(self)
        if method is None:
            return
        if not hasattr(self.repository, "list_financial_accounts"):
            QMessageBox.warning(self, "تنبيه", "مسار الخزينة والبنوك غير مفعل لهذه الفاتورة")
            return
        account_id = choose_financial_account(self, self.repository, method)
        if account_id is None:
            return
        try:
            self.repository.record_invoice_payment(
                invoice_type=self.invoice_type,
                invoice_id=int(row["id"]),
                amount=float(amount),
                payment_method=method,
                financial_account_id=account_id,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم تسجيل الحركة على الحساب المالي المحدد وتحديث حالة الدفع")
