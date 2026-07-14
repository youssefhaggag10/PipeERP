from app.database.connection import Database
from app.repositories.accounting_repository import AccountingRepository


class ReversibleAccountingRepository(AccountingRepository):
    """Adds auditable reversal of customer receipts and supplier payments."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self._ensure_reversal_schema()

    def _ensure_reversal_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_reversals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_transaction_id INTEGER NOT NULL UNIQUE,
                    original_transaction_number TEXT NOT NULL,
                    transaction_type TEXT NOT NULL,
                    partner_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    payment_method TEXT,
                    reference_type TEXT,
                    reference_id INTEGER,
                    sales_invoice_id INTEGER,
                    purchase_invoice_id INTEGER,
                    original_notes TEXT,
                    reversed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    reversal_reason TEXT
                )
                """
            )

    def reverse_payment(self, transaction_id: int, reason: str = "") -> None:
        with self.database.session(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM payment_transactions WHERE id = ?", (transaction_id,)
            ).fetchone()
            if row is None:
                raise ValueError("الحركة المالية غير موجودة أو تم عكسها بالفعل")

            columns = {item[1] for item in connection.execute(
                "PRAGMA table_info(payment_transactions)"
            ).fetchall()}
            sales_invoice_id = row["sales_invoice_id"] if "sales_invoice_id" in columns else None
            purchase_invoice_id = row["purchase_invoice_id"] if "purchase_invoice_id" in columns else None

            connection.execute(
                """
                INSERT INTO payment_reversals(
                    original_transaction_id, original_transaction_number,
                    transaction_type, partner_id, amount, payment_method,
                    reference_type, reference_id, sales_invoice_id,
                    purchase_invoice_id, original_notes, reversal_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(row["id"]), str(row["transaction_number"]),
                    str(row["transaction_type"]), int(row["partner_id"]),
                    float(row["amount"]), str(row["payment_method"] or ""),
                    row["reference_type"], row["reference_id"],
                    sales_invoice_id, purchase_invoice_id,
                    str(row["notes"] or ""), reason.strip(),
                ),
            )
            connection.execute("DELETE FROM payment_transactions WHERE id = ?", (transaction_id,))

    def list_transactions(self, limit: int = 500) -> list[dict]:
        active = super().list_transactions(limit)
        reversed_rows = self.database.fetch_all(
            """
            SELECT -pr.id AS id,
                   pr.original_transaction_number || '-REV' AS transaction_number,
                   pr.reversed_at AS transaction_date,
                   pr.transaction_type,
                   p.name AS partner_name,
                   -pr.amount AS amount,
                   COALESCE(pr.payment_method, '') AS payment_method,
                   pr.reference_type,
                   pr.reference_id,
                   'عكس الحركة ' || pr.original_transaction_number ||
                   CASE WHEN COALESCE(pr.reversal_reason, '') <> ''
                        THEN ' — ' || pr.reversal_reason ELSE '' END AS notes,
                   CASE
                       WHEN pr.reference_type = 'sale' THEN (
                           SELECT order_number FROM sales_orders WHERE id = pr.reference_id
                       )
                       WHEN pr.reference_type = 'purchase' THEN (
                           SELECT order_number FROM purchase_orders WHERE id = pr.reference_id
                       )
                       ELSE ''
                   END AS reference_number
            FROM payment_reversals pr
            JOIN partners p ON p.id = pr.partner_id
            ORDER BY pr.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = active + [dict(row) for row in reversed_rows]
        rows.sort(key=lambda item: str(item.get("transaction_date", "")), reverse=True)
        return rows[:limit]


__all__ = ["ReversibleAccountingRepository"]
