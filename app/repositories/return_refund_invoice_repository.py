from app.repositories.return_invoice_repository import ReturnInvoiceRepository
from app.services.invoice_service import payment_status


class ReturnRefundInvoiceRepository(ReturnInvoiceRepository):
    """Invoice view including returns, refunds and allocated customer receipts."""

    def list_invoices(self, invoice_type: str) -> list[dict]:
        rows = super().list_invoices(invoice_type)
        refund_rows = self.database.fetch_all(
            """
            SELECT invoice_id, COALESCE(SUM(amount), 0) AS total
            FROM return_refunds
            WHERE invoice_type = ?
            GROUP BY invoice_id
            """,
            (invoice_type,),
        )
        refunded_by_invoice = {
            int(row["invoice_id"]): float(row["total"]) for row in refund_rows
        }
        allocated_by_invoice: dict[int, float] = {}
        if invoice_type == "sales":
            allocation_rows = self.database.fetch_all(
                """
                SELECT sales_invoice_id AS invoice_id,
                       COALESCE(SUM(amount), 0) AS total
                FROM payment_allocations
                GROUP BY sales_invoice_id
                """
            )
            allocated_by_invoice = {
                int(row["invoice_id"]): float(row["total"])
                for row in allocation_rows
            }
        for item in rows:
            invoice_id = int(item["id"])
            cash_refunded = refunded_by_invoice.get(invoice_id, 0.0)
            recorded_paid = float(item["paid"])
            if invoice_type == "sales":
                recorded_paid = allocated_by_invoice.get(invoice_id, recorded_paid)
            effective_paid = max(0.0, recorded_paid - cash_refunded)
            net_total = float(item.get("net_total", item["total"]))
            item["cash_refunded"] = cash_refunded
            item["paid"] = effective_paid
            item["remaining"] = max(0.0, net_total - effective_paid)
            item["credit_balance"] = max(0.0, effective_paid - net_total)
            item["payment_status"] = payment_status(
                net_total,
                min(effective_paid, net_total),
                str(item["status"]),
            )
        return rows

    def get_sales_invoice_print_data(self, invoice_id: int) -> dict:
        document = super().get_sales_invoice_print_data(int(invoice_id))
        row = self.database.fetch_one(
            """
            SELECT
                COALESCE((
                    SELECT SUM(pa.amount) FROM payment_allocations pa
                    WHERE pa.sales_invoice_id = ?
                ), 0) AS allocated_paid,
                COALESCE((
                    SELECT SUM(rr.amount) FROM return_refunds rr
                    WHERE rr.invoice_type = 'sales' AND rr.invoice_id = ?
                      AND rr.refund_type = 'customer_refund'
                ), 0) AS cash_refunded
            """,
            (int(invoice_id), int(invoice_id)),
        )
        allocated = float(row["allocated_paid"] if row is not None else 0)
        if allocated <= 0:
            allocated = float(document.get("paid", 0) or 0)
        paid = max(
            0.0,
            allocated - float(row["cash_refunded"] if row is not None else 0),
        )
        total = float(document.get("total", 0) or 0)
        document["paid"] = paid
        document["remaining"] = max(0.0, total - paid)
        return document

    def list_financial_accounts(self) -> list[dict]:
        rows = super().list_financial_accounts()
        refund_rows = self.database.fetch_all(
            """
            SELECT financial_account_id,
                   COALESCE(SUM(CASE
                       WHEN refund_type = 'supplier_refund' THEN amount
                       WHEN refund_type = 'customer_refund' THEN -amount
                       ELSE 0 END), 0) AS total
            FROM return_refunds
            GROUP BY financial_account_id
            """
        )
        by_account = {
            int(row["financial_account_id"]): float(row["total"])
            for row in refund_rows
        }
        for item in rows:
            item["current_balance"] = float(item["current_balance"]) + by_account.get(
                int(item["id"]),
                0.0,
            )
        return rows

    def record_invoice_payment(self, **kwargs) -> int:
        invoice_type = str(kwargs.get("invoice_type"))
        invoice_id = int(kwargs.get("invoice_id"))
        amount = float(kwargs.get("amount", 0))
        matching = next(
            (
                row
                for row in self.list_invoices(invoice_type)
                if int(row["id"]) == invoice_id
            ),
            None,
        )
        if matching is None:
            raise ValueError("الفاتورة غير موجودة")
        remaining = float(matching["remaining"])
        if amount - remaining > 0.000001:
            raise ValueError(
                "المبلغ أكبر من صافي المتبقي بعد المرتجعات والاستردادات "
                f"({remaining:,.2f})"
            )
        transaction_id = super().record_invoice_payment(**kwargs)
        if invoice_type == "sales":
            with self.database.session(immediate=True) as connection:
                connection.execute(
                    """
                    INSERT OR REPLACE INTO payment_allocations(
                        transaction_id, sales_invoice_id, amount
                    ) VALUES (?, ?, ?)
                    """,
                    (int(transaction_id), invoice_id, amount),
                )
        return transaction_id


__all__ = ["ReturnRefundInvoiceRepository"]
