from app.repositories.invoice_repository import InvoiceRepository
from app.services.payment_account_rules import (
    account_matches_payment_method,
    expected_account_label,
)
from app.services.payment_service import post_order_payment


class TreasuryInvoiceRepository(InvoiceRepository):
    def list_financial_accounts(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT fa.id, fa.name, fa.account_type, fa.is_default,
                   fa.opening_balance
                   + COALESCE((SELECT SUM(CASE
                       WHEN pt.transaction_type = 'customer_receipt' THEN pt.amount
                       WHEN pt.transaction_type = 'supplier_payment' THEN -pt.amount
                       ELSE 0 END)
                     FROM payment_transactions pt
                     WHERE pt.financial_account_id = fa.id), 0)
                   + COALESCE((SELECT SUM(t.amount)
                     FROM financial_account_transfers t
                     WHERE t.to_account_id = fa.id), 0)
                   - COALESCE((SELECT SUM(t.amount)
                     FROM financial_account_transfers t
                     WHERE t.from_account_id = fa.id), 0)
                   + COALESCE((SELECT SUM(a.amount)
                     FROM financial_account_adjustments a
                     WHERE a.financial_account_id = fa.id), 0) AS current_balance
            FROM financial_accounts fa
            WHERE fa.is_active = 1
            ORDER BY fa.name
            """
        )
        return [dict(row) for row in rows]

    def record_invoice_payment(
        self,
        *,
        invoice_type: str,
        invoice_id: int,
        amount: float,
        payment_method: str,
        notes: str = "",
        financial_account_id: int | None = None,
    ) -> int:
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        if financial_account_id is None:
            raise ValueError("اختر حساب الخزينة أو البنك المستخدم في الحركة")

        account = self.database.fetch_one(
            """
            SELECT id, account_type
            FROM financial_accounts
            WHERE id = ? AND is_active = 1
            """,
            (int(financial_account_id),),
        )
        if account is None:
            raise ValueError("حساب الخزينة أو البنك غير موجود أو غير نشط")
        if not account_matches_payment_method(payment_method, str(account["account_type"])):
            raise ValueError(
                f"طريقة الدفع «{payment_method}» تتطلب {expected_account_label(payment_method)}"
            )

        if invoice_type == "sales":
            invoice_query = """
                SELECT id, status, total, customer_id AS partner_id,
                       sales_order_id AS order_id, invoice_number
                FROM sales_invoices
                WHERE id = ?
            """
            paid_query = """
                SELECT COALESCE(SUM(amount), 0) AS paid
                FROM payment_transactions
                WHERE sales_invoice_id = ?
            """
            link_query = """
                UPDATE payment_transactions
                SET sales_invoice_id = ?
                WHERE id = ?
            """
            transaction_type = "customer_receipt"
            reference_type = "sale"
        elif invoice_type == "purchase":
            invoice_query = """
                SELECT id, status, total, supplier_id AS partner_id,
                       purchase_order_id AS order_id, invoice_number
                FROM purchase_invoices
                WHERE id = ?
            """
            paid_query = """
                SELECT COALESCE(SUM(amount), 0) AS paid
                FROM payment_transactions
                WHERE purchase_invoice_id = ?
            """
            link_query = """
                UPDATE payment_transactions
                SET purchase_invoice_id = ?
                WHERE id = ?
            """
            transaction_type = "supplier_payment"
            reference_type = "purchase"
        else:
            raise ValueError("نوع الفاتورة غير صحيح")

        with self.database.session(immediate=True) as connection:
            invoice = connection.execute(invoice_query, (invoice_id,)).fetchone()
            if invoice is None:
                raise ValueError("الفاتورة غير موجودة")
            if invoice["status"] != "posted":
                raise ValueError("يجب اعتماد الفاتورة قبل تسجيل الدفع")

            paid = float(connection.execute(paid_query, (invoice_id,)).fetchone()["paid"])
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
                payment_method=payment_method,
                financial_account_id=int(financial_account_id),
            )
            connection.execute(link_query, (invoice_id, transaction_id))
            return transaction_id


__all__ = ["TreasuryInvoiceRepository"]
