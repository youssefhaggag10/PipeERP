from app.repositories.return_aware_treasury_repository import ReturnAwareTreasuryRepository


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


__all__ = ["ReturnRefundRepository"]