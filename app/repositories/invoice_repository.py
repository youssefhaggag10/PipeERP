from app.database.connection import Database
from app.services.invoice_service import payment_status
from app.services.payment_service import post_order_payment


class InvoiceRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def _ensure_invoices(self) -> None:
        """Synchronize invoices with fulfilled orders only.

        Draft orders may carry advance payments, but must not have invoices.
        Once an order is received/delivered, its invoice is created and posted,
        then any order-level advance payments are linked to that invoice.
        """
        with self.database.session(immediate=True) as connection:
            # Remove legacy invoices that were generated too early for draft orders.
            # Their payments remain linked to the order as advances.
            connection.execute(
                """
                UPDATE payment_transactions
                SET sales_invoice_id = NULL
                WHERE sales_invoice_id IN (
                    SELECT si.id
                    FROM sales_invoices si
                    JOIN sales_orders so ON so.id = si.sales_order_id
                    WHERE so.status = 'draft'
                )
                """
            )
            connection.execute(
                """
                DELETE FROM sales_invoices
                WHERE sales_order_id IN (
                    SELECT id FROM sales_orders WHERE status = 'draft'
                )
                """
            )
            connection.execute(
                """
                UPDATE payment_transactions
                SET purchase_invoice_id = NULL
                WHERE purchase_invoice_id IN (
                    SELECT pi.id
                    FROM purchase_invoices pi
                    JOIN purchase_orders po ON po.id = pi.purchase_order_id
                    WHERE po.status = 'draft'
                )
                """
            )
            connection.execute(
                """
                DELETE FROM purchase_invoices
                WHERE purchase_order_id IN (
                    SELECT id FROM purchase_orders WHERE status = 'draft'
                )
                """
            )

            sales_orders = connection.execute(
                """
                SELECT so.id, so.customer_id, so.notes,
                       COALESCE(SUM(sol.line_total), 0) AS total
                FROM sales_orders so
                LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
                WHERE so.status = 'delivered'
                  AND NOT EXISTS (
                      SELECT 1 FROM sales_invoices si WHERE si.sales_order_id = so.id
                  )
                GROUP BY so.id, so.customer_id, so.notes
                ORDER BY so.id
                """
            ).fetchall()
            for order in sales_orders:
                connection.execute(
                    """
                    INSERT INTO sales_invoices(
                        invoice_number, sales_order_id, customer_id, invoice_date,
                        status, total, notes, posted_at
                    )
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'posted', ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"SI{int(order[0]):05d}",
                        order[0],
                        order[1],
                        float(order[3]),
                        order[2] or "",
                    ),
                )

            purchase_orders = connection.execute(
                """
                SELECT po.id, po.supplier_id, po.notes,
                       COALESCE(SUM(pol.line_total), 0) AS total
                FROM purchase_orders po
                LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
                WHERE po.status = 'received'
                  AND NOT EXISTS (
                      SELECT 1 FROM purchase_invoices pi WHERE pi.purchase_order_id = po.id
                  )
                GROUP BY po.id, po.supplier_id, po.notes
                ORDER BY po.id
                """
            ).fetchall()
            for order in purchase_orders:
                connection.execute(
                    """
                    INSERT INTO purchase_invoices(
                        invoice_number, purchase_order_id, supplier_id, invoice_date,
                        status, total, notes, posted_at
                    )
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'posted', ?, ?, CURRENT_TIMESTAMP)
                    """,
                    (
                        f"PI{int(order[0]):05d}",
                        order[0],
                        order[1],
                        float(order[3]),
                        order[2] or "",
                    ),
                )

            # Repair old fulfilled orders whose invoice was still a draft.
            connection.execute(
                """
                UPDATE sales_invoices
                SET status = 'posted', posted_at = COALESCE(posted_at, CURRENT_TIMESTAMP)
                WHERE status = 'draft'
                  AND sales_order_id IN (
                      SELECT id FROM sales_orders WHERE status = 'delivered'
                  )
                """
            )
            connection.execute(
                """
                UPDATE purchase_invoices
                SET status = 'posted', posted_at = COALESCE(posted_at, CURRENT_TIMESTAMP)
                WHERE status = 'draft'
                  AND purchase_order_id IN (
                      SELECT id FROM purchase_orders WHERE status = 'received'
                  )
                """
            )

            # Transfer advance payments from the order to the active invoice.
            connection.execute(
                """
                UPDATE payment_transactions
                SET sales_invoice_id = (
                    SELECT si.id
                    FROM sales_invoices si
                    WHERE si.sales_order_id = payment_transactions.reference_id
                      AND si.status <> 'cancelled'
                )
                WHERE reference_type = 'sale'
                  AND sales_invoice_id IS NULL
                  AND EXISTS (
                      SELECT 1
                      FROM sales_invoices si
                      WHERE si.sales_order_id = payment_transactions.reference_id
                        AND si.status <> 'cancelled'
                  )
                """
            )
            connection.execute(
                """
                UPDATE payment_transactions
                SET purchase_invoice_id = (
                    SELECT pi.id
                    FROM purchase_invoices pi
                    WHERE pi.purchase_order_id = payment_transactions.reference_id
                      AND pi.status <> 'cancelled'
                )
                WHERE reference_type = 'purchase'
                  AND purchase_invoice_id IS NULL
                  AND EXISTS (
                      SELECT 1
                      FROM purchase_invoices pi
                      WHERE pi.purchase_order_id = payment_transactions.reference_id
                        AND pi.status <> 'cancelled'
                  )
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

    def get_sales_invoice_print_data(self, invoice_id: int) -> dict:
        self._ensure_invoices()
        row = self.database.fetch_one(
            """
            SELECT si.id, si.invoice_number, si.invoice_date, si.status, si.total,
                   COALESCE(si.notes, '') AS notes, so.order_number,
                   p.name AS customer_name, COALESCE(p.code, '') AS customer_code,
                   COALESCE(p.phone, '') AS customer_phone,
                   COALESCE(p.address, '') AS customer_address,
                   COALESCE((
                       SELECT SUM(pt.amount) FROM payment_transactions pt
                       WHERE pt.sales_invoice_id = si.id
                   ), 0) AS paid,
                   COALESCE((
                       SELECT GROUP_CONCAT(DISTINCT NULLIF(TRIM(pt.payment_method), ''))
                       FROM payment_transactions pt
                       WHERE pt.sales_invoice_id = si.id
                   ), '') AS payment_methods
            FROM sales_invoices si
            JOIN sales_orders so ON so.id = si.sales_order_id
            JOIN partners p ON p.id = si.customer_id
            WHERE si.id = ?
            """,
            (invoice_id,),
        )
        if row is None:
            raise ValueError("فاتورة المبيعات غير موجودة")
        if row["status"] != "posted":
            raise ValueError("يمكن طباعة فواتير المبيعات المعتمدة فقط")

        lines = self.database.fetch_all(
            """
            SELECT product.code, product.name, sol.quantity, sol.unit,
                   sol.unit_price, sol.line_total
            FROM sales_invoices si
            JOIN sales_order_lines sol ON sol.sales_order_id = si.sales_order_id
            JOIN products product ON product.id = sol.product_id
            WHERE si.id = ?
            ORDER BY sol.id
            """,
            (invoice_id,),
        )
        result = dict(row)
        result["lines"] = [dict(line) for line in lines]
        result["remaining"] = max(0.0, float(result["total"]) - float(result["paid"]))
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
                    "SELECT COALESCE(SUM(amount), 0) AS paid "
                    f"FROM payment_transactions WHERE {invoice_column} = ?",
                    (invoice_id,),
                ).fetchone()["paid"]
            )
            if paid > 0.000001:
                raise ValueError("اعكس سندات الدفع المرتبطة بالفاتورة أولًا قبل إلغائها")
            connection.execute(
                f"UPDATE {table} SET status = 'cancelled', "
                "cancelled_at = CURRENT_TIMESTAMP WHERE id = ?",
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
                f"SELECT id, status, total, {partner_column} AS partner_id, "
                f"{order_column} AS order_id, invoice_number "
                f"FROM {table} WHERE id = ?",
                (invoice_id,),
            ).fetchone()
            if invoice is None:
                raise ValueError("الفاتورة غير موجودة")
            if invoice["status"] != "posted":
                raise ValueError("يجب اعتماد الفاتورة قبل تسجيل الدفع")
            paid = float(
                connection.execute(
                    "SELECT COALESCE(SUM(amount), 0) AS paid "
                    f"FROM payment_transactions WHERE {invoice_column} = ?",
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
                "UPDATE payment_transactions SET payment_method = ?, "
                f"{invoice_column} = ? WHERE id = ?",
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
