from app.database.connection import Database
from app.repositories.reversible_accounting_repository import ReversibleAccountingRepository
from app.services.payment_service import post_order_payment

EPSILON = 0.000001


class TreasuryRepository(ReversibleAccountingRepository):
    """Operational cash, bank, and wallet accounts without a full general ledger."""

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self._ensure_treasury_schema()

    def _ensure_treasury_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL UNIQUE,
                    name TEXT NOT NULL,
                    account_type TEXT NOT NULL CHECK(
                        account_type IN ('cash', 'bank', 'wallet', 'other')
                    ),
                    opening_balance REAL NOT NULL DEFAULT 0,
                    is_default INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS financial_account_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transfer_number TEXT NOT NULL UNIQUE,
                    transfer_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    from_account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    to_account_id INTEGER NOT NULL REFERENCES financial_accounts(id),
                    amount REAL NOT NULL CHECK(amount > 0),
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    CHECK(from_account_id <> to_account_id)
                )
                """
            )
            payment_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(payment_transactions)").fetchall()
            }
            if "financial_account_id" not in payment_columns:
                connection.execute(
                    "ALTER TABLE payment_transactions ADD COLUMN financial_account_id "
                    "INTEGER REFERENCES financial_accounts(id)"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_payment_financial_account "
                "ON payment_transactions(financial_account_id, transaction_date, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transfer_from_account "
                "ON financial_account_transfers(from_account_id, transfer_date, id)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_transfer_to_account "
                "ON financial_account_transfers(to_account_id, transfer_date, id)"
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO financial_accounts(
                    code, name, account_type, opening_balance, is_default, notes
                ) VALUES ('CASH-MAIN', 'الخزينة الرئيسية', 'cash', 0, 1,
                          'الحساب الافتراضي للحركات القديمة والجديدة')
                """
            )
            default_row = connection.execute(
                "SELECT id FROM financial_accounts WHERE is_default = 1 AND is_active = 1 "
                "ORDER BY id LIMIT 1"
            ).fetchone()
            if default_row is None:
                default_row = connection.execute(
                    "SELECT id FROM financial_accounts WHERE is_active = 1 ORDER BY id LIMIT 1"
                ).fetchone()
                if default_row is not None:
                    connection.execute(
                        "UPDATE financial_accounts SET is_default = CASE WHEN id = ? THEN 1 ELSE 0 END",
                        (default_row[0],),
                    )
            if default_row is not None:
                connection.execute(
                    "UPDATE payment_transactions SET financial_account_id = ? "
                    "WHERE financial_account_id IS NULL",
                    (default_row[0],),
                )

    def list_financial_accounts(self, *, active_only: bool = True) -> list[dict]:
        where = "WHERE fa.is_active = 1" if active_only else ""
        rows = self.database.fetch_all(
            f"""
            SELECT fa.id, fa.code, fa.name, fa.account_type, fa.opening_balance,
                   fa.is_default, fa.is_active, COALESCE(fa.notes, '') AS notes,
                   fa.opening_balance
                   + COALESCE((
                       SELECT SUM(CASE
                           WHEN pt.transaction_type = 'customer_receipt' THEN pt.amount
                           WHEN pt.transaction_type = 'supplier_payment' THEN -pt.amount
                           ELSE 0 END)
                       FROM payment_transactions pt
                       WHERE pt.financial_account_id = fa.id
                   ), 0)
                   + COALESCE((
                       SELECT SUM(t.amount) FROM financial_account_transfers t
                       WHERE t.to_account_id = fa.id
                   ), 0)
                   - COALESCE((
                       SELECT SUM(t.amount) FROM financial_account_transfers t
                       WHERE t.from_account_id = fa.id
                   ), 0) AS current_balance
            FROM financial_accounts fa
            {where}
            ORDER BY fa.is_default DESC, fa.name
            """
        )
        return [dict(row) for row in rows]

    def create_financial_account(
        self,
        *,
        code: str,
        name: str,
        account_type: str,
        opening_balance: float = 0,
        is_default: bool = False,
        notes: str = "",
    ) -> int:
        code = code.strip().upper()
        name = name.strip()
        if not code or not name:
            raise ValueError("كود واسم الحساب مطلوبان")
        if account_type not in {"cash", "bank", "wallet", "other"}:
            raise ValueError("نوع الحساب غير صحيح")
        with self.database.session(immediate=True) as connection:
            if is_default:
                connection.execute("UPDATE financial_accounts SET is_default = 0")
            cursor = connection.execute(
                """
                INSERT INTO financial_accounts(
                    code, name, account_type, opening_balance, is_default, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (code, name, account_type, float(opening_balance), int(is_default), notes.strip()),
            )
            return int(cursor.lastrowid)

    def set_default_financial_account(self, account_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            row = connection.execute(
                "SELECT id FROM financial_accounts WHERE id = ? AND is_active = 1",
                (account_id,),
            ).fetchone()
            if row is None:
                raise ValueError("الحساب المالي غير موجود أو غير نشط")
            connection.execute("UPDATE financial_accounts SET is_default = 0")
            connection.execute(
                "UPDATE financial_accounts SET is_default = 1 WHERE id = ?",
                (account_id,),
            )

    def get_default_financial_account_id(self) -> int:
        row = self.database.fetch_one(
            "SELECT id FROM financial_accounts WHERE is_default = 1 AND is_active = 1 "
            "ORDER BY id LIMIT 1"
        )
        if row is None:
            raise ValueError("لا يوجد حساب مالي افتراضي")
        return int(row["id"])

    def account_balance(self, account_id: int) -> float:
        for row in self.list_financial_accounts(active_only=False):
            if int(row["id"]) == int(account_id):
                return float(row["current_balance"])
        raise ValueError("الحساب المالي غير موجود")

    def transfer_between_accounts(
        self,
        *,
        from_account_id: int,
        to_account_id: int,
        amount: float,
        notes: str = "",
    ) -> int:
        amount = float(amount)
        if amount <= 0:
            raise ValueError("مبلغ التحويل يجب أن يكون أكبر من صفر")
        if int(from_account_id) == int(to_account_id):
            raise ValueError("لا يمكن التحويل إلى نفس الحساب")
        if self.account_balance(from_account_id) + EPSILON < amount:
            raise ValueError("رصيد الحساب المحول منه غير كافٍ")
        with self.database.session(immediate=True) as connection:
            accounts = connection.execute(
                "SELECT id FROM financial_accounts WHERE id IN (?, ?) AND is_active = 1",
                (from_account_id, to_account_id),
            ).fetchall()
            if len(accounts) != 2:
                raise ValueError("أحد الحسابات غير موجود أو غير نشط")
            next_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM financial_account_transfers"
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO financial_account_transfers(
                    transfer_number, from_account_id, to_account_id, amount, notes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (f"TR{next_id:06d}", from_account_id, to_account_id, amount, notes.strip()),
            )
            return int(cursor.lastrowid)

    def list_account_movements(self, limit: int = 1000) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT pt.transaction_date AS movement_date,
                   pt.transaction_number AS movement_number,
                   fa.name AS account_name,
                   CASE WHEN pt.transaction_type = 'customer_receipt'
                        THEN 'تحصيل عميل' ELSE 'سداد مورد' END AS movement_type,
                   CASE WHEN pt.transaction_type = 'customer_receipt'
                        THEN pt.amount ELSE 0 END AS amount_in,
                   CASE WHEN pt.transaction_type = 'supplier_payment'
                        THEN pt.amount ELSE 0 END AS amount_out,
                   COALESCE(p.name, '') AS counterparty,
                   COALESCE(pt.notes, '') AS notes
            FROM payment_transactions pt
            JOIN financial_accounts fa ON fa.id = pt.financial_account_id
            LEFT JOIN partners p ON p.id = pt.partner_id
            UNION ALL
            SELECT t.transfer_date, t.transfer_number, destination.name,
                   'تحويل وارد', t.amount, 0, source.name, COALESCE(t.notes, '')
            FROM financial_account_transfers t
            JOIN financial_accounts source ON source.id = t.from_account_id
            JOIN financial_accounts destination ON destination.id = t.to_account_id
            UNION ALL
            SELECT t.transfer_date, t.transfer_number, source.name,
                   'تحويل صادر', 0, t.amount, destination.name, COALESCE(t.notes, '')
            FROM financial_account_transfers t
            JOIN financial_accounts source ON source.id = t.from_account_id
            JOIN financial_accounts destination ON destination.id = t.to_account_id
            ORDER BY movement_date DESC, movement_number DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows]

    def record_payment(
        self,
        *,
        transaction_type: str,
        partner_id: int,
        amount: float,
        payment_method: str = "نقدي",
        reference_id: int | None = None,
        notes: str = "",
        financial_account_id: int | None = None,
    ) -> int:
        expected_partner_type = "customer" if transaction_type == "customer_receipt" else "supplier"
        if transaction_type not in {"customer_receipt", "supplier_payment"}:
            raise ValueError("نوع الحركة المالية غير صحيح")
        if amount <= 0:
            raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
        financial_account_id = (
            int(financial_account_id)
            if financial_account_id is not None
            else self.get_default_financial_account_id()
        )
        if transaction_type == "supplier_payment":
            if self.account_balance(financial_account_id) + EPSILON < float(amount):
                raise ValueError("رصيد حساب السداد غير كافٍ")

        with self.database.session(immediate=True) as connection:
            partner = connection.execute(
                "SELECT id FROM partners WHERE id = ? AND partner_type = ? AND is_active = 1",
                (partner_id, expected_partner_type),
            ).fetchone()
            if partner is None:
                raise ValueError("العميل أو المورد غير موجود")
            account = connection.execute(
                "SELECT id FROM financial_accounts WHERE id = ? AND is_active = 1",
                (financial_account_id,),
            ).fetchone()
            if account is None:
                raise ValueError("حساب الخزينة أو البنك غير موجود")

            reference_type = None
            if reference_id is not None:
                reference_type = "sale" if expected_partner_type == "customer" else "purchase"
                order_table = "sales_orders" if reference_type == "sale" else "purchase_orders"
                partner_column = "customer_id" if reference_type == "sale" else "supplier_id"
                line_table = (
                    "sales_order_lines" if reference_type == "sale" else "purchase_order_lines"
                )
                order_fk = "sales_order_id" if reference_type == "sale" else "purchase_order_id"
                order = connection.execute(
                    f"""
                    SELECT o.{partner_column} AS partner_id,
                           COALESCE(SUM(l.line_total), 0) AS total,
                           COALESCE((SELECT SUM(pt.amount) FROM payment_transactions pt
                                     WHERE pt.reference_type = ? AND pt.reference_id = o.id), 0) AS paid
                    FROM {order_table} o
                    LEFT JOIN {line_table} l ON l.{order_fk} = o.id
                    WHERE o.id = ?
                    GROUP BY o.id, o.{partner_column}
                    """,
                    (reference_type, reference_id),
                ).fetchone()
                if order is None or int(order["partner_id"]) != partner_id:
                    raise ValueError("المستند لا يخص الطرف المحدد")
                remaining = float(order["total"]) - float(order["paid"])
                if float(amount) - remaining > EPSILON:
                    raise ValueError(f"المبلغ أكبر من المتبقي على المستند ({remaining:,.2f})")

            transaction_id = post_order_payment(
                connection,
                transaction_type=transaction_type,
                partner_id=partner_id,
                amount=float(amount),
                reference_type=reference_type,
                reference_id=reference_id,
                notes=notes,
                payment_method=payment_method,
                financial_account_id=financial_account_id,
            )
            if reference_id is not None:
                invoice_table = (
                    "sales_invoices" if reference_type == "sale" else "purchase_invoices"
                )
                invoice_column = (
                    "sales_invoice_id" if reference_type == "sale" else "purchase_invoice_id"
                )
                invoice_order_column = (
                    "sales_order_id" if reference_type == "sale" else "purchase_order_id"
                )
                invoice = connection.execute(
                    f"SELECT id FROM {invoice_table} WHERE {invoice_order_column} = ? AND status = 'posted'",
                    (reference_id,),
                ).fetchone()
                if invoice is not None:
                    connection.execute(
                        f"UPDATE payment_transactions SET {invoice_column} = ? WHERE id = ?",
                        (invoice["id"], transaction_id),
                    )
            return transaction_id

    def list_transactions(self, limit: int = 500) -> list[dict]:
        rows = super().list_transactions(limit)
        account_map = {
            int(row["id"]): str(row["name"])
            for row in self.list_financial_accounts(active_only=False)
        }
        active_ids = [int(row.get("id", 0)) for row in rows if int(row.get("id", 0)) > 0]
        linked: dict[int, int] = {}
        if active_ids:
            placeholders = ",".join("?" for _ in active_ids)
            linked_rows = self.database.fetch_all(
                f"SELECT id, financial_account_id FROM payment_transactions WHERE id IN ({placeholders})",
                tuple(active_ids),
            )
            linked = {
                int(row["id"]): int(row["financial_account_id"])
                for row in linked_rows
                if row["financial_account_id"] is not None
            }
        for row in rows:
            row["financial_account_name"] = account_map.get(
                linked.get(int(row.get("id", 0)), 0), "-"
            )
        return rows


__all__ = ["TreasuryRepository"]
