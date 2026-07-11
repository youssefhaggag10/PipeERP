from app.database.connection import Database
from app.services.invoice_service import payment_status
from app.services.payment_service import post_order_payment


class InvoiceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_invoices(self, invoice_type: str) -> list[dict]:
        if invoice_type == "sales":
            rows = self.database.fetch_all(
                """
                SELECT si.id, si.invoice_number, so.order_number, si.invoice_date,
                       si.status, si.total, p.name AS partner_name,
                       COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.sales_invoice_id = si.id), 0) AS paid
                FROM sales_invoices si
                JOIN sales_orders so ON so.id = si.sales_order_id
                JOIN partners p ON p.id = si.customer_id
                ORDER BY si.id DESC
                """
            )
        elif invoice_type == "purchase":
            rows = self.database.fetch_all(
                """
                SELECT pi.id, pi.invoice_number, po.order_number, pi.invoice_date,
                       pi.status, pi.total, p.name AS partner_name,
                       COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                           WHERE pt.purchase_invoice_id = pi.id), 0) AS paid
                FROM purchase_invoices pi
                JOIN purchase_orders po ON po.id = pi.purchase_order_id
                JOIN partners p ON p.id = pi.supplier_id
                ORDER BY pi.id DESC
                """
            )
        else:
            raise ValueError("نوع الفاتورة غير صحيح")

        result = []
        for row in rows:
            item = dict(row)
            item["remaining"] = max(0.0, float(item["total"]) - float(item["paid"]))
            item["payment_status"] = payment_status(
                float(item["total"]), float(item["paid"]), str(item["status"])
            )
            result.append(item)
        return result

    def post_invoice(self, invoice_type: str, invoice_id: int) -> None:
        table = self._table(invoice_type)
        with self.database.session(immediate=True) as connection:
            invoice = connection.execute(
                f"SELECT status FROM {table} WHERE id = ?", (invoice_id,)
            ).fetchone()
            if invoice is None:
                raise ValueError("الفاتورة غير موجودة")
            if invoice["status"] == "cancelled":
                raise ValueError("لا يمكن اعتماد فاتورة ملغاة")
            connection.execute(
                f"UPDATE {table} SET status = 'posted', posted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (invoice_id,),
            )

    def cancel_invoice(self, invoice_type: str, invoice_id: int) -> None:
        table = self._table(invoice_type)
        invoice_column = "sales_invoice_id" if invoice_type == "sales" else "purchase_invoice_id"
        with self.database.session(immediate=True) as connection:
            invoice = connection.execute(
                f"SELECT status FROM {table} WHERE id = ?", (invoice_id,)
            ).fetchone()
            if invoice is None:
                raise ValueError("الفاتورة غير موجودة")
            paid = float(
                connection.execute(
                    f"SELECT COALESCE(SUM(amount), 0) AS paid FROM payment_transactions WHERE {invoice_column} = ?",
                    (invoice_id,),
                ).fetchone()["paid"]
            )
            if paid > 0.000001:
                raise ValueError("اعكس سندات الدفع المرتبطة بالفاتورة أولًا قبل إلغائها")
            connection.execute(
                f"UPDATE {table} SET status = 'cancelled', cancelled_at = CURRENT_TIMESTAMP WHERE id = ?",
                (invoice_id,),
            )

    def record_invoice_payment(
        self,
        *,
        invoice_type: str,
        invoice_id: int,
        amount: float,
        payment_method: str,
        notes: str = "",
    ) -> int:
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        if invoice_type == "sales":
            table = "sales_invoices"
            partner_column = "customer_id"
            order_column = "sales_order_id"
            invoice_column = "sales_invoice_id"
            transaction_type = "customer_receipt"
            reference_type = "sale"
        elif invoice_type == "purchase":
            table = "purchase_invoices"
            partner_column = "supplier_id"
            order_column = "purchase_order_id"
            invoice_column = "purchase_invoice_id"
            transaction_type = "supplier_payment"
            reference_type = "purchase"
        else:
            raise ValueError("نوع الفاتورة غير صحيح")

        with self.database.session(immediate=True) as connection:
            invoice = connection.execute(
                f"SELECT id, status, total, {partner_column} AS partner_id, {order_column} AS order_id, invoice_number FROM {table} WHERE id = ?",
                (invoice_id,),
            ).fetchone()
            if invoice is None:
                raise ValueError("الفاتورة غير موجودة")
            if invoice["status"] != "posted":
                raise ValueError("يجب اعتماد الفاتورة قبل تسجيل الدفع")
            paid = float(
                connection.execute(
                    f"SELECT COALESCE(SUM(amount), 0) AS paid FROM payment_transactions WHERE {invoice_column} = ?",
                    (invoice_id,),
                ).fetchone()["paid"]
            )
            remaining = float(invoice["total"]) - paid
            if amount - remaining > 0.000001:
                raise ValueError(f"المبلغ أكبر من المتبقي على الفاتورة ({remaining:,.2f})")
            transaction_id = post_order_payment(
                connection,
                transaction_type=transaction_type,
                partner_id=int(invoice["partner_id"]),
                amount=amount,
                reference_type=reference_type,
                reference_id=int(invoice["order_id"]),
                notes=notes or f"دفعة على الفاتورة {invoice['invoice_number']}",
            )
            connection.execute(
                f"UPDATE payment_transactions SET payment_method = ?, {invoice_column} = ? WHERE id = ?",
                (payment_method.strip() or "نقدي", invoice_id, transaction_id),
            )
            return transaction_id

    @staticmethod
    def _table(invoice_type: str) -> str:
        if invoice_type == "sales":
            return "sales_invoices"
        if invoice_type == "purchase":
            return "purchase_invoices"
        raise ValueError("نوع الفاتورة غير صحيح")
