from app.repositories.return_aware_treasury_repository import ReturnAwareTreasuryRepository
from app.services.payment_account_rules import (
    account_matches_payment_method,
    expected_account_label,
)


EPSILON = 0.000001


class ReturnRefundRepository(ReturnAwareTreasuryRepository):
    """Accounting totals and treasury movements after cash refunds for returns."""

    def __init__(self, database) -> None:
        super().__init__(database)
        self._ensure_return_refund_schema()

    def _ensure_return_refund_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS return_refunds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    refund_number TEXT NOT NULL UNIQUE,
                    refund_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    refund_type TEXT NOT NULL CHECK(
                        refund_type IN ('supplier_refund', 'customer_refund')
                    ),
                    partner_id INTEGER NOT NULL REFERENCES partners(id),
                    invoice_type TEXT NOT NULL CHECK(invoice_type IN ('sales', 'purchase')),
                    invoice_id INTEGER NOT NULL,
                    amount REAL NOT NULL CHECK(amount > 0),
                    payment_method TEXT NOT NULL,
                    financial_account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_return_refunds_partner
                ON return_refunds(partner_id, refund_date, id);

                CREATE INDEX IF NOT EXISTS idx_return_refunds_invoice
                ON return_refunds(invoice_type, invoice_id, refund_date, id);

                CREATE INDEX IF NOT EXISTS idx_return_refunds_account
                ON return_refunds(financial_account_id, refund_date, id);
                """
            )

    def _refunds_by_partner(self, refund_type: str) -> dict[int, float]:
        rows = self.database.fetch_all(
            """
            SELECT partner_id, COALESCE(SUM(amount), 0) AS total
            FROM return_refunds
            WHERE refund_type = ?
            GROUP BY partner_id
            """,
            (refund_type,),
        )
        return {int(row["partner_id"]): float(row["total"]) for row in rows}

    def list_partner_balances(self, partner_type: str) -> list[dict]:
        rows = super().list_partner_balances(partner_type)
        refund_type = "customer_refund" if partner_type == "customer" else "supplier_refund"
        refunds = self._refunds_by_partner(refund_type)

        for item in rows:
            advances = float(item.get("advances", 0))
            total_paid = float(item.get("paid", 0))
            invoice_payments = max(0.0, total_paid - advances)
            refunded = refunds.get(int(item["id"]), 0.0)

            item["paid"] = invoice_payments
            item["refunds_total"] = refunded
            item["balance"] = (
                float(item["opening_balance"])
                + float(item["invoices_total"])
                - invoice_payments
                - advances
                + refunded
            )
        return rows

    def dashboard_summary(self) -> dict:
        result = super().dashboard_summary()
        row = self.database.fetch_one(
            """
            SELECT
                COALESCE(SUM(CASE WHEN refund_type = 'supplier_refund'
                                  THEN amount ELSE 0 END), 0) AS supplier_refunds,
                COALESCE(SUM(CASE WHEN refund_type = 'customer_refund'
                                  THEN amount ELSE 0 END), 0) AS customer_refunds
            FROM return_refunds
            """
        )
        supplier_refunds = float(row["supplier_refunds"] if row is not None else 0)
        customer_refunds = float(row["customer_refunds"] if row is not None else 0)
        result["supplier_refunds"] = supplier_refunds
        result["customer_refunds"] = customer_refunds
        result["payables"] = float(result.get("payables", 0)) + supplier_refunds
        result["receivables"] = float(result.get("receivables", 0)) + customer_refunds
        return result

    def list_refundable_invoices(
        self,
        refund_type: str,
        partner_id: int | None = None,
    ) -> list[dict]:
        if refund_type == "supplier_refund":
            invoice_type = "purchase"
            invoice_table = "purchase_invoices"
            partner_column = "supplier_id"
            invoice_payment_column = "purchase_invoice_id"
            order_table = "purchase_orders"
            order_fk = "purchase_order_id"
        elif refund_type == "customer_refund":
            invoice_type = "sales"
            invoice_table = "sales_invoices"
            partner_column = "customer_id"
            invoice_payment_column = "sales_invoice_id"
            order_table = "sales_orders"
            order_fk = "sales_order_id"
        else:
            raise ValueError("نوع الاسترداد غير صحيح")

        rows = self.database.fetch_all(
            f"""
            SELECT invoice.id, invoice.invoice_number,
                   orders.order_number,
                   invoice.{partner_column} AS partner_id,
                   invoice.total AS original_total,
                   COALESCE((
                       SELECT SUM(ir.total)
                       FROM invoice_returns ir
                       WHERE ir.invoice_type = ? AND ir.invoice_id = invoice.id
                   ), 0) AS returned_total,
                   COALESCE((
                       SELECT SUM(pt.amount)
                       FROM payment_transactions pt
                       WHERE pt.{invoice_payment_column} = invoice.id
                   ), 0) AS paid,
                   COALESCE((
                       SELECT SUM(rr.amount)
                       FROM return_refunds rr
                       WHERE rr.invoice_type = ? AND rr.invoice_id = invoice.id
                   ), 0) AS refunded
            FROM {invoice_table} invoice
            JOIN {order_table} orders ON orders.id = invoice.{order_fk}
            WHERE invoice.status = 'posted'
              AND (? IS NULL OR invoice.{partner_column} = ?)
            ORDER BY invoice.id DESC
            """,
            (invoice_type, invoice_type, partner_id, partner_id),
        )
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            net_total = max(
                0.0,
                float(item["original_total"]) - float(item["returned_total"]),
            )
            refundable = max(
                0.0,
                float(item["paid"]) - net_total - float(item["refunded"]),
            )
            if refundable > EPSILON:
                item["invoice_type"] = invoice_type
                item["net_total"] = net_total
                item["refundable"] = refundable
                result.append(item)
        return result

    def record_return_refund(
        self,
        *,
        refund_type: str,
        partner_id: int,
        invoice_id: int,
        amount: float,
        payment_method: str,
        financial_account_id: int,
        notes: str = "",
    ) -> int:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        if refund_type == "supplier_refund":
            expected_partner_type = "supplier"
            invoice_type = "purchase"
            prefix = "SRF"
        elif refund_type == "customer_refund":
            expected_partner_type = "customer"
            invoice_type = "sales"
            prefix = "CRF"
        else:
            raise ValueError("نوع الاسترداد غير صحيح")

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

        partner = self.database.fetch_one(
            """
            SELECT id FROM partners
            WHERE id = ? AND partner_type = ? AND is_active = 1
            """,
            (int(partner_id), expected_partner_type),
        )
        if partner is None:
            raise ValueError("العميل أو المورد غير موجود أو غير نشط")

        matching = next(
            (
                row
                for row in self.list_refundable_invoices(refund_type, int(partner_id))
                if int(row["id"]) == int(invoice_id)
            ),
            None,
        )
        if matching is None:
            raise ValueError("لا يوجد مبلغ قابل للاسترداد على الفاتورة المحددة")
        refundable = float(matching["refundable"])
        if amount - refundable > EPSILON:
            raise ValueError(
                f"المبلغ أكبر من المتاح للاسترداد على الفاتورة ({refundable:,.2f})"
            )

        with self.database.session(immediate=True) as connection:
            next_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM return_refunds"
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO return_refunds(
                    refund_number, refund_type, partner_id, invoice_type,
                    invoice_id, amount, payment_method, financial_account_id, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"{prefix}{next_id:06d}",
                    refund_type,
                    int(partner_id),
                    invoice_type,
                    int(invoice_id),
                    amount,
                    payment_method.strip() or "نقدي",
                    int(financial_account_id),
                    notes.strip(),
                ),
            )
            return int(cursor.lastrowid)

    def list_financial_accounts(self, *, active_only: bool = True) -> list[dict]:
        rows = super().list_financial_accounts(active_only=active_only)
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
            item["current_balance"] = (
                float(item["current_balance"]) + by_account.get(int(item["id"]), 0.0)
            )
        return rows

    def list_account_movements(self, limit: int = 1000) -> list[dict]:
        rows = super().list_account_movements(limit)
        refund_rows = self.database.fetch_all(
            """
            SELECT rr.refund_date AS movement_date,
                   rr.refund_number AS movement_number,
                   fa.name AS account_name,
                   CASE WHEN rr.refund_type = 'supplier_refund'
                        THEN 'استرداد من مورد' ELSE 'رد مبلغ لعميل' END AS movement_type,
                   CASE WHEN rr.refund_type = 'supplier_refund'
                        THEN rr.amount ELSE 0 END AS amount_in,
                   CASE WHEN rr.refund_type = 'customer_refund'
                        THEN rr.amount ELSE 0 END AS amount_out,
                   p.name AS counterparty,
                   COALESCE(rr.notes, '') AS notes
            FROM return_refunds rr
            JOIN financial_accounts fa ON fa.id = rr.financial_account_id
            JOIN partners p ON p.id = rr.partner_id
            ORDER BY rr.refund_date DESC, rr.id DESC
            """
        )
        rows.extend(dict(row) for row in refund_rows)
        rows.sort(
            key=lambda row: (
                str(row.get("movement_date", "")),
                str(row.get("movement_number", "")),
            ),
            reverse=True,
        )
        return rows[:limit]

    def list_transactions(self, limit: int = 500) -> list[dict]:
        rows = super().list_transactions(limit)
        refund_rows = self.database.fetch_all(
            """
            SELECT -rr.id AS id,
                   rr.refund_number AS transaction_number,
                   rr.refund_date AS transaction_date,
                   rr.refund_type AS transaction_type,
                   p.name AS partner_name,
                   rr.amount,
                   rr.payment_method,
                   fa.name AS financial_account_name,
                   CASE WHEN rr.invoice_type = 'purchase'
                        THEN (SELECT invoice_number FROM purchase_invoices WHERE id = rr.invoice_id)
                        ELSE (SELECT invoice_number FROM sales_invoices WHERE id = rr.invoice_id)
                   END AS reference_number,
                   COALESCE(rr.notes, '') AS notes
            FROM return_refunds rr
            JOIN partners p ON p.id = rr.partner_id
            JOIN financial_accounts fa ON fa.id = rr.financial_account_id
            ORDER BY rr.refund_date DESC, rr.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows.extend(dict(row) for row in refund_rows)
        rows.sort(key=lambda item: str(item.get("transaction_date", "")), reverse=True)
        return rows[:limit]


__all__ = ["ReturnRefundRepository"]