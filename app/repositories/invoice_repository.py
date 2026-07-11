from app.database.connection import Database
from app.services.invoice_service import payment_status
from app.services.payment_service import post_order_payment


class InvoiceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _ensure_invoices(self) -> None:
        with self.database.session(immediate=True) as connection:
            sales_orders = connection.execute(
                """
                SELECT so.id, so.customer_id, so.order_date, so.status, so.notes,
                       COALESCE(SUM(sol.line_total), 0) AS total
                FROM sales_orders so
                LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
                WHERE NOT EXISTS (
                    SELECT 1 FROM sales_invoices si WHERE si.sales_order_id = so.id
                )
                GROUP BY so.id, so.customer_id, so.order_date, so.status, so.notes
                ORDER BY so.id
                """
            ).fetchall()
            for order in sales_orders:
                paid = float(
                    connection.execute(
                        """
                        SELECT COALESCE(SUM(amount), 0) AS paid
                        FROM payment_transactions
                        WHERE reference_type = 'sale' AND reference_id = ?
                        """,
                        (order[0],),
                    ).fetchone()["paid"]
                )
                status = "posted" if str(order[3]) == "delivered" or paid > 0 else "draft"
                connection.execute(
                    """
                    INSERT INTO sales_invoices(
                        invoice_number, sales_order_id, customer_id, invoice_date,
                        status, total, notes, posted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'posted' THEN CURRENT_TIMESTAMP ELSE NULL END)
                    """,
                    (
                        f"SI{int(order[0]):05d}", order[0], order[1], order[2], status,
                        float(order[5]), order[4] or "", status,
                    ),
                )

            purchase_orders = connection.execute(
                """
                SELECT po.id, po.supplier_id, po.order_date, po.status, po.notes,
                       COALESCE(SUM(pol.line_total), 0) AS total
                FROM purchase_orders po
                LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
                WHERE NOT EXISTS (
                    SELECT 1 FROM purchase_invoices pi WHERE pi.purchase_order_id = po.id
                )
                GROUP BY po.id, po.supplier_id, po.order_date, po.status, po.notes
                ORDER BY po.id
                """
            ).fetchall()
            for order in purchase_orders:
                paid = float(
                    connection.execute(
                        """
                        SELECT COALESCE(SUM(amount), 0) AS paid
                        FROM payment_transactions
                        WHERE reference_type = 'purchase' AND reference_id = ?
                        """,
                        (order[0],),
                    ).fetchone()["paid"]
                )
                status = "posted" if str(order[3]) == "received" or paid > 0 else "draft"
                connection.execute(
                    """
                    INSERT INTO purchase_invoices(
                        invoice_number, purchase_order_id, supplier_id, invoice_date,
                        status, total, notes, posted_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'posted' THEN CURRENT_TIMESTAMP ELSE NULL END)
                    """,
                    (
                        f"PI{int(order[0]):05d}", order[0], order[1], order[2], status,
                        float(order[5]), order[4] or "", status,
                    ),
                )

            connection.execute(
                """
                UPDATE payment_transactions
                SET sales_invoice_id = (
                    SELECT si.id FROM sales_invoices si
                    WHERE si.sales_order_id = payment_transactions.reference_id
                )
                WHERE reference_type = 'sale' AND sales_invoice_id IS NULL
                """
            )
            connection.execute(
                """
                UPDATE payment_transactions
                SET purchase_invoice_id = (
                    SELECT pi.id FROM purchase_invoices pi
                    WHERE pi.purchase_order_id = payment_transactions.reference_id
                )
                WHERE reference_type = 'purchase' AND purchase_invoice_id IS NULL
                """
            )

    def list_invoices(self, invoice_type: str) -> list[dict]:
        self._ensure_invoices()
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
