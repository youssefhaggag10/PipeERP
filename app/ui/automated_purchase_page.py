from datetime import datetime
from uuid import uuid4

from PySide6.QtWidgets import QMessageBox

from app.ui.accounting_order_pages import PurchaseAccountingPage
from app.ui.order_details_dialog import OrderDetailsDialog


class AutomatedPurchaseAccountingPage(PurchaseAccountingPage):
    """Purchase page with automatic lots and separated supplier/inventory costing."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.lot_input.setPlaceholderText("سيُنشئ النظام رقم الدفعة تلقائيًا")
        self.lot_input.setToolTip(
            "اترك الحقل فارغًا ليُنشئ النظام رقم Lot فريدًا تلقائيًا، أو أدخل رقم المورد عند الحاجة."
        )
        self.manufacturing_price_input.setToolTip(
            "تكلفة تجهيز داخلية لكل كجم تضاف لتكلفة المخزون فقط، ولا تدخل في مديونية المورد."
        )
        self.lines_table.setHorizontalHeaderLabels(
            [
                "الكود",
                "الصنف",
                "رقم الدفعة",
                "إجمالي الكمية",
                "الوحدة",
                "سعر شراء المورد",
                "تجهيز داخلي/كجم",
                "الفقد",
                "صافي المخزن",
                "تكلفة المخزون/وحدة",
                "مستحق المورد",
            ]
        )
        self.total_label.setText("إجمالي مستحق المورد: 0.00")

    def add_or_update_line(self) -> None:
        if not self.lot_input.text().strip():
            product_id = self.product_input.currentData()
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            product_token = str(product_id or "ITEM")
            generated = f"PUR-{product_token}-{stamp}-{uuid4().hex[:6].upper()}"
            self.lot_input.setText(generated)

        product_index = self.product_input.currentIndex()
        if product_index < 0 or product_index >= len(self.products):
            QMessageBox.warning(self, "تنبيه", "أضف صنفًا أولًا")
            return

        try:
            quantity = float(self.qty_input.text().strip())
            unit_price = float(self.price_input.text().strip() or 0)
            manufacturing_unit_cost = float(
                self.manufacturing_price_input.text().strip() or 0
            )
            loss_text = self.loss_input.text().strip()
            purchase_loss_quantity = (
                float(loss_text) if loss_text else self._default_purchase_loss(quantity)
            )
        except ValueError:
            QMessageBox.warning(self, "تنبيه", "الكمية والأسعار والفقد يجب أن تكون أرقامًا")
            return

        lot_number = self.lot_input.text().strip()
        if (
            quantity <= 0
            or unit_price < 0
            or manufacturing_unit_cost < 0
            or purchase_loss_quantity < 0
            or purchase_loss_quantity >= quantity
            or not lot_number
        ):
            QMessageBox.warning(
                self,
                "تنبيه",
                "أدخل دفعة وكمية صحيحة وأسعارًا غير سالبة، والفقد أقل من الكمية",
            )
            return

        product = self.products[product_index]
        net_quantity = quantity - purchase_loss_quantity
        supplier_total = quantity * unit_price
        internal_processing_total = quantity * manufacturing_unit_cost
        inventory_total = supplier_total + internal_processing_total

        line = {
            "product_id": int(product["id"]),
            "code": product["code"],
            "name": product["name"],
            "lot_number": lot_number,
            "quantity": quantity,
            "unit": self.unit_input.text().strip() or product["unit"],
            "unit_price": unit_price,
            "manufacturing_unit_cost": manufacturing_unit_cost,
            "purchase_loss_quantity": purchase_loss_quantity,
            "net_quantity": net_quantity,
            "inventory_unit_cost": inventory_total / net_quantity,
            "line_total": supplier_total,
        }

        if self.editing_line_index is None:
            self.lines.append(line)
        else:
            self.lines[self.editing_line_index] = line
        self.refresh_lines_table()
        self.clear_line_editor()

    def refresh_lines_table(self) -> None:
        super().refresh_lines_table()
        total = sum(float(line["line_total"]) for line in self.lines)
        self.total_label.setText(f"إجمالي مستحق المورد: {total:,.2f}")

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
                ("التاريخ", order["order_date"]),
                ("الحالة", self.status_label(order["status"])),
                ("المدفوع للمورد", f"{float(order['paid']):,.2f}"),
                ("المتبقي للمورد", f"{float(order['remaining']):,.2f}"),
                ("الملاحظات", order["notes"] or ""),
            ],
            columns=[
                "الكود",
                "الصنف",
                "الدفعة",
                "الإجمالي كجم",
                "الوحدة",
                "سعر شراء المورد",
                "تجهيز داخلي/كجم",
                "الفقد",
                "صافي المخزن",
                "تكلفة المخزون",
                "مستحق المورد",
            ],
            rows=rows,
            total=float(order["total"]),
            parent=self,
        )
        dialog.exec()


__all__ = ["AutomatedPurchaseAccountingPage"]
