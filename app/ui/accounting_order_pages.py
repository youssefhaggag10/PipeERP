from PySide6.QtWidgets import (
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTableWidgetItem,
    QWidget,
)

from app.ui.order_details_dialog import OrderDetailsDialog
from app.ui.purchase_page import PurchasePage
from app.ui.sales_page import SalesPage


class _PaymentOrderMixin:
    paid_input: QLineEdit

    def _install_payment_fields(self, label_text: str) -> None:
        self.paid_input = QLineEdit("0")
        self.paid_input.setPlaceholderText("0.00")
        payment_form = QFormLayout()
        payment_form.addRow(label_text, self.paid_input)
        payment_note = QLabel("يمكن تسجيل باقي الدفعات لاحقًا من شاشة الحسابات")
        payment_note.setObjectName("subtitleLabel")
        container = QWidget()
        container_layout = QFormLayout(container)
        container_layout.addRow(payment_note)
        container_layout.addRow(label_text, self.paid_input)
        self.layout().insertWidget(3, container)

        self.warehouse_input.setEnabled(False)
        self.warehouse_input.setToolTip("النظام يعمل على مخزن واحد فقط: المصنع")

    def _paid_amount(self) -> float:
        try:
            amount = float(self.paid_input.text().strip() or 0)
        except ValueError as error:
            raise ValueError("المدفوع يجب أن يكون رقمًا") from error
        if amount < 0:
            raise ValueError("المدفوع لا يمكن أن يكون سالبًا")
        return amount


class PurchaseAccountingPage(_PaymentOrderMixin, PurchasePage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_payment_fields("المدفوع عند إنشاء الأمر")
        self.orders_table.setColumnCount(10)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر", "المورد", "الأصناف", "عدد البنود", "المخزن",
                "التاريخ", "الحالة", "الإجمالي", "المدفوع", "المتبقي",
            ]
        )
        self.reload_orders()

    def reload_orders(self) -> None:
        self.orders = self.purchase_repository.list_orders()
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            summary = str(order["product_summary"])
            visible_summary = summary if len(summary) <= 45 else summary[:42] + "..."
            values = [
                order["order_number"], order["supplier_name"], visible_summary,
                order["line_count"], order["warehouse_name"], order["order_date"],
                self.status_label(order["status"]), f"{float(order['total']):,.2f}",
                f"{float(order['paid']):,.2f}", f"{float(order['remaining']):,.2f}",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    item.setToolTip(summary)
                self.orders_table.setItem(row_index, column_index, item)

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
        self.reload_orders()
        QMessageBox.information(self, "تم", f"تم حفظ أمر الشراء رقم {order_id} كمسودة")

    def view_selected_order(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        order = self.purchase_repository.get_order_details(order_id)
        rows = [
            [
                line["code"], line["name"], line["lot_number"],
                f"{float(line['quantity']):g}", line["unit"],
                f"{float(line['unit_price']):,.2f}", f"{float(line['line_total']):,.2f}",
            ]
            for line in order["lines"]
        ]
        dialog = OrderDetailsDialog(
            title=f"تفاصيل أمر الشراء {order['order_number']}",
            header_fields=[
                ("المورد", order["supplier_name"]), ("المخزن", order["warehouse_name"]),
                ("التاريخ", order["order_date"]), ("الحالة", self.status_label(order["status"])),
                ("المدفوع", f"{float(order['paid']):,.2f}"),
                ("المتبقي", f"{float(order['remaining']):,.2f}"),
                ("الملاحظات", order["notes"] or ""),
            ],
            columns=["الكود", "الصنف", "الدفعة", "الكمية", "الوحدة", "السعر", "الإجمالي"],
            rows=rows, total=float(order["total"]), parent=self,
        )
        dialog.exec()


class SalesAccountingPage(_PaymentOrderMixin, SalesPage):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._install_payment_fields("المحصل عند إنشاء الأمر")
        self.orders_table.setColumnCount(10)
        self.orders_table.setHorizontalHeaderLabels(
            [
                "رقم الأمر", "العميل", "الأصناف", "عدد البنود", "المخزن",
                "التاريخ", "الحالة", "الإجمالي", "المدفوع", "المتبقي",
            ]
        )
        self.reload_orders()

    def reload_orders(self) -> None:
        self.orders = self.sales_repository.list_orders()
        self.orders_table.setRowCount(len(self.orders))
        for row_index, order in enumerate(self.orders):
            summary = str(order["product_summary"])
            visible_summary = summary if len(summary) <= 45 else summary[:42] + "..."
            values = [
                order["order_number"], order["customer_name"], visible_summary,
                order["line_count"], order["warehouse_name"], order["order_date"],
                self.status_label(order["status"]), f"{float(order['total']):,.2f}",
                f"{float(order['paid']):,.2f}", f"{float(order['remaining']):,.2f}",
            ]
            for column_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column_index == 2:
                    item.setToolTip(summary)
                self.orders_table.setItem(row_index, column_index, item)

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
        self.reload_orders()
        QMessageBox.information(self, "تم", f"تم حفظ أمر البيع رقم {order_id} كمسودة")

    def view_selected_order(self) -> None:
        order_id = self.selected_order_id()
        if order_id is None:
            return
        order = self.sales_repository.get_order_details(order_id)
        rows = [
            [
                line["code"], line["name"], f"{float(line['quantity']):g}", line["unit"],
                f"{float(line['unit_price']):,.2f}", f"{float(line['line_total']):,.2f}",
            ]
            for line in order["lines"]
        ]
        dialog = OrderDetailsDialog(
            title=f"تفاصيل أمر البيع {order['order_number']}",
            header_fields=[
                ("العميل", order["customer_name"]), ("المخزن", order["warehouse_name"]),
                ("التاريخ", order["order_date"]), ("الحالة", self.status_label(order["status"])),
                ("المدفوع", f"{float(order['paid']):,.2f}"),
                ("المتبقي", f"{float(order['remaining']):,.2f}"),
                ("الملاحظات", order["notes"] or ""),
            ],
            columns=["الكود", "الصنف", "الكمية", "الوحدة", "السعر", "الإجمالي"],
            rows=rows, total=float(order["total"]), parent=self,
        )
        dialog.exec()
