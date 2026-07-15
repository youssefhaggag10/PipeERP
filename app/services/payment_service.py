from sqlite3 import Connection


def _ensure_financial_account_schema(connection: Connection) -> int:
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
    columns = {
        str(row[1]) for row in connection.execute(
            "PRAGMA table_info(payment_transactions)"
        ).fetchall()
    }
    if "financial_account_id" not in columns:
        connection.execute(
            "ALTER TABLE payment_transactions ADD COLUMN financial_account_id "
            "INTEGER REFERENCES financial_accounts(id)"
        )
    connection.execute(
        """
        INSERT OR IGNORE INTO financial_accounts(
            code, name, account_type, opening_balance, is_default, notes
        ) VALUES ('CASH-MAIN', 'الخزينة الرئيسية', 'cash', 0, 1,
                  'الحساب الافتراضي للحركات القديمة والجديدة')
        """
    )
    row = connection.execute(
        "SELECT id FROM financial_accounts WHERE is_default = 1 AND is_active = 1 "
        "ORDER BY id LIMIT 1"
    ).fetchone()
    if row is None:
        row = connection.execute(
            "SELECT id FROM financial_accounts WHERE is_active = 1 ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            raise ValueError("لا يوجد حساب مالي متاح")
        connection.execute("UPDATE financial_accounts SET is_default = 0")
        connection.execute(
            "UPDATE financial_accounts SET is_default = 1 WHERE id = ?",
            (row[0],),
        )
    return int(row[0])


def post_order_payment(
    connection: Connection,
    *,
    transaction_type: str,
    partner_id: int,
    amount: float,
    reference_type: str | None,
    reference_id: int | None,
    notes: str = "",
    payment_method: str = "نقدي",
    financial_account_id: int | None = None,
) -> int:
    if amount <= 0:
        raise ValueError("قيمة الدفع يجب أن تكون أكبر من صفر")
    default_account_id = _ensure_financial_account_schema(connection)
    financial_account_id = int(financial_account_id or default_account_id)
    account = connection.execute(
        "SELECT id FROM financial_accounts WHERE id = ? AND is_active = 1",
        (financial_account_id,),
    ).fetchone()
    if account is None:
        raise ValueError("حساب الخزينة أو البنك غير موجود أو غير نشط")

    next_id = int(
        connection.execute(
            "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM payment_transactions"
        ).fetchone()["next_id"]
    )
    prefix = "CR" if transaction_type == "customer_receipt" else "SP"
    transaction_number = f"{prefix}{next_id:06d}"
    cursor = connection.execute(
        """
        INSERT INTO payment_transactions(
            transaction_number, transaction_type, partner_id, amount,
            payment_method, reference_type, reference_id, notes,
            financial_account_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transaction_number,
            transaction_type,
            partner_id,
            amount,
            payment_method.strip() or "نقدي",
            reference_type,
            reference_id,
            notes.strip(),
            financial_account_id,
        ),
    )
    return int(cursor.lastrowid)
