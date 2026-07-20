from app.repositories.return_invoice_repository import ReturnInvoiceRepository
from app.services.invoice_service import payment_status


class ReturnRefundInvoiceRepository(ReturnInvoiceRepository):
    """Invoice view that deducts settled return refunds from displayed payments."""

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
        refunded_by_invoice = {int(row["invoice_id"]): float(row["total"]) for row in refund_rows}
        for item in rows:
            cash_refunded = refunded_by_invoice.get(int(item["id"]), 0.0)
            effective_paid = max(0.0, float(item["paid"]) - cash_refunded)
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
        by_account = {int(row["financial_account_id"]): float(row["total"]) for row in refund_rows}
        for item in rows:
            item["current_balance"] = float(item["current_balance"]) + by_account.get(
                int(item["id"]), 0.0
            )
        return rows

    def record_invoice_payment(self, **kwargs) -> int:
        invoice_type = str(kwargs.get("invoice_type"))
        invoice_id = int(kwargs.get("invoice_id"))
        amount = float(kwargs.get("amount", 0))
        matching = next(
            (row for row in self.list_invoices(invoice_type) if int(row["id"]) == invoice_id),
            None,
        )
        if matching is None:
            raise ValueError("الفاتورة غير موجودة")
        remaining = float(matching["remaining"])
        if amount - remaining > 0.000001:
            raise ValueError(
                f"المبلغ أكبر من صافي المتبقي بعد المرتجعات والاستردادات ({remaining:,.2f})"
            )
        return super().record_invoice_payment(**kwargs)


__all__ = ["ReturnRefundInvoiceRepository"]
