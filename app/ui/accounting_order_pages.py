from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.repositories.invoice_repository import InvoiceRepository
from app.services.invoice_service import INVOICE_STATUS_LABELS
from app.ui.order_details_dialog import OrderDetailsDialog
from app.ui.purchase_page import PurchasePage
from app.ui.sales_page import SalesPage
from app.utils.datetime_utils import format_egypt_datetime

INVOICE_COLORS = {
    "draft": QColor("#64748B"),
    "posted": QColor("#2563EB"),
    "cancelled": QColor("#DC2626"),
}


class _PaymentOrderMixin:
    paid_input: QLineEdit
    search_input: QLineEdit

    def _install_payment_fields(self, label_text: str) -> None:
        self.paid_input = QLineEdit("0")
        self.paid_input.setPlaceholderText("0.00")
        payment_note = QLabel("يمكن تسجيل باقي الدفعات لاحقًا من شاشة الحسابات")
        payment_note.setObjectName("subtitleLabel")
        container = QWidget()
        container_layout = QFormLayout(container)
        container_layout.addRow(payment_note)
        container_layout.addRow(label_text, self.paid_input)
        self.layout().insertWidget(3, container)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "بحث برقم الأمر أو رقم الفاتورة أو الاسم أو رقم الهاتف"
        )
        self.search_input.textChanged.connect(self._apply_search)
        self.layout().insertWidget(self.layout().count() - 1, self.search_input)

        self.warehouse_input.setEnabled(False)
        self.warehouse_input.setToolTip("النظام يعمل على مخزن واحد فقط: المصنع")
        self.orders_table.setEditTriggers(QTableWidget.NoEditTriggers)

    def _paid_amount(self) -> float:
        try:
            amount = float(self.paid_input.text().strip() or 0)
        except ValueError as error:
            raise ValueError("المدفوع يجب أن يكون رقمًا") from error
        if amount < 0:
            raise ValueError("المدفوع لا يمكن أن يكون سالبًا")
        return amount

    def _apply_search(self) -> None:
        search_input = getattr(self, "search_input", None)
        orders_table = getattr(self, "orders_table", None)
        if search_input is None or orders_table is None:
            return

        query = search_input.text().strip().casefold()
        for row_index, order in enumerate(self.orders):
            haystack = " ".join(
                str(order.get(key, ""))
                for key in (
                    "order_number",
                    "invoice_number",
                    "partner_name",
                    "partner_phone",
                    "invoice_status",
                )
            ).casefold()
            orders_table.setRowHidden(row_index, bool(query) and query not in haystack)

    def _record_selected_payment(self, invoice_type: str) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        self.invoice_repository._ensure_invoices()
        if invoice_type == "sales":
            row = self.sales_repository.database.fetch_one(
                "SELECT id, status, total FROM sales_invoices WHERE sales_order_id = ?",
                (order_id,),
            )
            action_label = "تحصيل"
        else:
            row = self.purchase_repository.database.fetch_one(
                "SELECT id, status, total FROM purchase_invoices WHERE purchase_order_id = ?",
                (order_id,),
            )
            action_label = "سداد"
        if row is None:
            QMessageBox.warning(self, "تنبيه", "لم يتم العثور على فاتورة مرتبطة بالأمر")
            return
        if row["status"] == "draft":
            self.invoice_repository.post_invoice(invoice_type, int(row["id"]))
        invoices = self.invoice_repository.list_invoices(invoice_type)
        invoice = next((item for item in invoices if int(item["id"]) == int(row["id"])), None)
        if invoice is None:
            return
        remaining = float(invoice["remaining"])
        if remaining <= 0.000001:
            QMessageBox.information(self, "تنبيه", "الفاتورة مدفوعة بالكامل")
            return
        amount, accepted = QInputDialog.getDouble(
            self,
            f"تسجيل {action_label}",
            f"المتبقي: {remaining:,.2f}\nأدخل المبلغ:",
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
            self.invoice_repository.record_invoice_payment(
                invoice_type=invoice_type,
                invoice_id=int(row["id"]),
                amount=float(amount),
                payment_method=str(method),
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload_orders()
        QMessageBox.information(self, "تم", f"تم تسجيل {action_label} وربطه بالفاتورة")

    @staticmethod
    def _invoice_status_label(status: str) -> str:
        return INVOICE_STATUS_LABELS.get(status, "—" if not status else status)

    @staticmethod
    def _style_invoice_status(item: QTableWidgetItem, status: str) -> None:
        color = INVOICE_COLORS.get(status)
        if color is not None:
            item.setBackground(color)
            item.setForeground(QColor("white"))


class PurchaseAccountingPage(_PaymentOrderMixin, PurchasePage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.invoice_repository = InvoiceRepository(self.purchase_repository.database)
        self._install_payment_fields("المدفوع عند إنشاء الأمر")

        pay_button = QPushButton("تسجيل سداد للأمر المحدد")
        pay_button.clicked.connect(lambda: self._record_selected_payment("purchase"))
        self.layout().insertWidget(self.layout().count() - 1, pay_button)

        self.orders_table.setColumnCount(12)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر",
                "الوقت",
                "المورد",
                "الأصناف",
                "عدد البنود",
                "المخزن",
                "حالة الأمر",
                "الإجمالي",
                "المدفوع",
                "المتبقي",
                "رقم الفاتورة",
                "حالة الفاتورة",
            ]
        )
        self.reload_orders()

    def reload_orders(self) -> None:
        rows = self.purchase_repository.database.fetch_all(
            """
            SELECT po.id, po.order_number, po.order_date, po.status,
                   p.name AS partner_name, COALESCE(p.phone, '') AS partner_phone,
                   w.name AS warehouse_name, COUNT(pol.id) AS line_count,
                   COALESCE(GROUP_CONCAT(product.name, '، '), '') AS product_summary,
                   COALESCE(SUM(pol.line_total), 0) AS total,
                   COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                       WHERE pt.reference_type = 'purchase'
                         AND pt.reference_id = po.id), 0) AS paid,
                   COALESCE(pi.invoice_number, '') AS invoice_number,
                   COALESCE(pi.status, '') AS invoice_status
            FROM purchase_orders po
            JOIN partners p ON p.id = po.supplier_id
            JOIN warehouses w ON w.id = po.warehouse_id
            LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
            LEFT JOIN products product ON product.id = pol.product_id
            LEFT JOIN purchase_invoices pi ON pi.purchase_order_id = po.id
            GROUP BY po.id, po.order_number, po.order_date, po.status,
                     p.name, p.phone, w.name, pi.invoice_number, pi.status
            ORDER BY po.id DESC
            """
        )
        self.orders = []
        for row in rows:
            item = dict(row)
            item["remaining"] = float(item["total"]) - float(item["paid"])
            self.orders.append(item)
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            summary = str(order["product_summary"])
            visible_summary = summary if len(summary) <= 45 else summary[:42] + "..."
            values = [
                order["order_number"],
                format_egypt_datetime(order["order_date"]),
                order["partner_name"],
                visible_summary,
                order["line_count"],
                order["warehouse_name"],
                self.status_label(order["status"]),
                f"{float(order['total']):,.2f}",
                f"{float(order['paid']):,.2f}",
                f"{float(order['remaining']):,.2f}",
                order["invoice_number"],
                self._invoice_status_label(str(order["invoice_status"])),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 3:
                    item.setToolTip(summary)
                if column_index == 11:
                    self._style_invoice_status(item, str(order["invoice_status"]))
                self.orders_table.setItem(row_index, column_index, item)
        self._apply_search()

    def create_order(self) -> None:
        if self.supplier_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر المورد")
            return
        try:
            order_id = self.purchase_repository.create_order_with_lines(
                supplier_id=int(self.supplier_input.currentData()),
                lines=self.lines,
                notes=self.notes_input.text(),
                paid_amount=self._paid_amount(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.lines.clear()
        self.notes_input.clear()
        self.paid_input.setText("0")
        self.refresh_lines_table()
        self.invoice_repository._ensure_invoices()
        self.reload_orders()
        QMessageBox.information(self, "تم", f"تم حفظ أمر الشراء رقم {order_id} كمسودة")

    def receive_selected(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        try:
            self.purchase_repository.receive_order(order_id)
            self.invoice_repository._ensure_invoices()
            invoice = self.purchase_repository.database.fetch_one(
                "SELECT id FROM purchase_invoices WHERE purchase_order_id = ?", (order_id,)
            )
            if invoice is not None:
                self.invoice_repository.post_invoice("purchase", int(invoice["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload_orders()
        QMessageBox.information(
            self, "تم", "تم استلام الأمر وتحديث المخزون واعتماد فاتورة المشتريات تلقائيًا"
        )

    def view_selected_order(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        order = self.purchase_repository.get_order_details(order_id)
        rows = [
            [
                line["code"],
                line["name"],
                line["lot_number"],
                f"{float(line['quantity']):g}",
                line["unit"],
                f"{float(line['unit_price']):,.2f}",
                f"{float(line['manufacturing_unit_cost']):,.2f}",
                f"{float(line['purchase_loss_quantity']):g}",
                f"{float(line['net_quantity']):g}",
                f"{float(line['inventory_unit_cost']):,.4f}",
                f"{float(line['line_total']):,.2f}",
            ]
            for line in order["lines"]
        ]
        dialog = OrderDetailsDialog(
            title=f"تفاصيل أمر الشراء {order['order_number']}",
            header_fields=[
                ("المورد", order["supplier_name"]),
                ("المخزن", order["warehouse_name"]),
                ("التاريخ", format_egypt_datetime(order["order_date"])),
                ("الحالة", self.status_label(order["status"])),
                ("المدفوع", f"{float(order['paid']):,.2f}"),
                ("المتبقي", f"{float(order['remaining']):,.2f}"),
                ("الملاحظات", order["notes"] or ""),
            ],
            columns=[
                "الكود",
                "الصنف",
                "الدفعة",
                "الإجمالي كجم",
                "الوحدة",
                "سعر الشراء",
                "تصنيع/كجم",
                "الفقد",
                "صافي المخزن",
                "تكلفة المخزون",
                "الإجمالي",
            ],
            rows=rows,
            total=float(order["total"]),
            parent=self,
        )
        dialog.exec()


class SalesAccountingPage(_PaymentOrderMixin, SalesPage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.invoice_repository = InvoiceRepository(self.sales_repository.database)
        self._install_payment_fields("المحصل عند إنشاء الأمر")

        pay_button = QPushButton("تسجيل تحصيل للأمر المحدد")
        pay_button.clicked.connect(lambda: self._record_selected_payment("sales"))
        self.layout().insertWidget(self.layout().count() - 1, pay_button)

        self.orders_table.setColumnCount(12)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر",
                "الوقت",
                "العميل",
                "الأصناف",
                "عدد البنود",
                "المخزن",
                "حالة الأمر",
                "الإجمالي",
                "المدفوع",
                "المتبقي",
                "رقم الفاتورة",
                "حالة الفاتورة",
            ]
        )
        self.reload_orders()

    def reload_orders(self) -> None:
        rows = self.sales_repository.database.fetch_all(
            """
            SELECT so.id, so.order_number, so.order_date, so.status,
                   p.name AS partner_name, COALESCE(p.phone, '') AS partner_phone,
                   w.name AS warehouse_name, COUNT(sol.id) AS line_count,
                   COALESCE(GROUP_CONCAT(product.name, '، '), '') AS product_summary,
                   COALESCE(SUM(sol.line_total), 0) AS total,
                   COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                       WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id), 0) AS paid,
                   COALESCE(si.invoice_number, '') AS invoice_number,
                   COALESCE(si.status, '') AS invoice_status
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
            LEFT JOIN products product ON product.id = sol.product_id
            LEFT JOIN sales_invoices si ON si.sales_order_id = so.id
            GROUP BY so.id, so.order_number, so.order_date, so.status,
                     p.name, p.phone, w.name, si.invoice_number, si.status
            ORDER BY so.id DESC
            """
        )
        self.orders = []
        for row in rows:
            item = dict(row)
            item["remaining"] = float(item["total"]) - float(item["paid"])
            self.orders.append(item)
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            summary = str(order["product_summary"])
            visible_summary = summary if len(summary) <= 45 else summary[:42] + "..."
            values = [
                order["order_number"],
                format_egypt_datetime(order["order_date"]),
                order["partner_name"],
                visible_summary,
                order["line_count"],
                order["warehouse_name"],
                self.status_label(order["status"]),
                f"{float(order['total']):,.2f}",
                f"{float(order['paid']):,.2f}",
                f"{float(order['remaining']):,.2f}",
                order["invoice_number"],
                self._invoice_status_label(str(order["invoice_status"])),
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 3:
                    item.setToolTip(summary)
                if column_index == 11:
                    self._style_invoice_status(item, str(order["invoice_status"]))
                self.orders_table.setItem(row_index, column_index, item)
        self._apply_search()

    def create_order(self) -> None:
        if self.customer_input.currentData() is None:
            QMessageBox.warning(self, "تنبيه", "اختر العميل")
            return
        try:
            order_id = self.sales_repository.create_order_with_lines(
                customer_id=int(self.customer_input.currentData()),
                lines=self.lines,
                notes=self.notes_input.text(),
                paid_amount=self._paid_amount(),
            )
        except (KeyError, TypeError, ValueError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.lines.clear()
        self.notes_input.clear()
        self.paid_input.setText("0")
        self.refresh_lines_table()
        self.invoice_repository._ensure_invoices()
        self.reload_orders()
        QMessageBox.information(self, "تم", f"تم حفظ أمر البيع رقم {order_id} كمسودة")

    def deliver_selected(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        try:
            self.sales_repository.deliver_order(order_id)
            self.invoice_repository._ensure_invoices()
            invoice = self.sales_repository.database.fetch_one(
                "SELECT id FROM sales_invoices WHERE sales_order_id = ?", (order_id,)
            )
            if invoice is not None:
                self.invoice_repository.post_invoice("sales", int(invoice["id"]))
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload_orders()
        QMessageBox.information(
            self, "تم", "تم تسليم الأمر وتحديث المخزون واعتماد فاتورة المبيعات تلقائيًا"
        )

    def view_selected_order(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        order = self.sales_repository.get_order_details(order_id)
        rows = [
            [
                line["code"],
                line["name"],
                f"{float(line['quantity']):g}",
                line["unit"],
                f"{float(line['unit_price']):,.2f}",
                f"{float(line['line_total']):,.2f}",
            ]
            for line in order["lines"]
        ]
        dialog = OrderDetailsDialog(
            title=f"تفاصيل أمر البيع {order['order_number']}",
            header_fields=[
                ("العميل", order["customer_name"]),
                ("المخزن", order["warehouse_name"]),
                ("التاريخ", format_egypt_datetime(order["order_date"])),
                ("الحالة", self.status_label(order["status"])),
                ("المدفوع", f"{float(order['paid']):,.2f}"),
                ("المتبقي", f"{float(order['remaining']):,.2f}"),
                ("الملاحظات", order["notes"] or ""),
            ],
            columns=["الكود", "الصنف", "الكمية", "الوحدة", "السعر", "الإجمالي"],
            rows=rows,
            total=float(order["total"]),
            parent=self,
        )
        dialog.exec()
