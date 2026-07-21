from __future__ import annotations

from sqlite3 import Connection

SCHEMA_VERSION = 10
DATABASE_VERSION = "0.10.0"


def _column_exists(connection: Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(str(row[1]) == column_name for row in rows)


def _add_columns(
    connection: Connection,
    table_name: str,
    columns: dict[str, str],
) -> None:
    for column_name, definition in columns.items():
        if not _column_exists(connection, table_name, column_name):
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}"
            )


def ensure_sales_finance_v10_schema(connection: Connection) -> None:
    """Apply the non-destructive weight-invoice and statement migration.

    The original migration runner owns versions 1-9. This focused migration
    extends sales, invoice and payment tables atomically while preserving every
    legacy row, then advances SQLite ``user_version`` to 10.
    """

    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            "قاعدة البيانات أحدث من إصدار البرنامج الحالي. حدّث البرنامج قبل فتحها."
        )

    _add_columns(
        connection,
        "sales_orders",
        {
            "weight_mode": "TEXT NOT NULL DEFAULT 'total_card'",
            "weight_pricing_mode": "TEXT NOT NULL DEFAULT 'uniform'",
        },
    )
    _add_columns(
        connection,
        "sales_invoices",
        {
            "invoice_type": "TEXT NOT NULL DEFAULT 'standard'",
            "discount_amount": "REAL NOT NULL DEFAULT 0",
            "transport_amount": "REAL NOT NULL DEFAULT 0",
            "tax_amount": "REAL NOT NULL DEFAULT 0",
            "net_total": "REAL NOT NULL DEFAULT 0",
        },
    )
    _add_columns(
        connection,
        "sales_weight_cards",
        {
            "sales_invoice_id": "INTEGER REFERENCES sales_invoices(id)",
            "weight_mode": "TEXT NOT NULL DEFAULT 'total_card'",
            "pricing_mode": "TEXT NOT NULL DEFAULT 'uniform'",
            "use_vehicle_scale": "INTEGER NOT NULL DEFAULT 0",
            "discount_amount": "REAL NOT NULL DEFAULT 0",
            "transport_amount": "REAL NOT NULL DEFAULT 0",
            "tax_amount": "REAL NOT NULL DEFAULT 0",
            "net_amount": "REAL NOT NULL DEFAULT 0",
        },
    )
    _add_columns(
        connection,
        "sales_weight_card_lines",
        {
            "actual_weight_kg": "REAL NOT NULL DEFAULT 0",
            "price_per_kg": "REAL NOT NULL DEFAULT 0",
            "notes": "TEXT NOT NULL DEFAULT ''",
        },
    )

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS payment_allocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL
                REFERENCES payment_transactions(id) ON DELETE CASCADE,
            sales_invoice_id INTEGER NOT NULL
                REFERENCES sales_invoices(id) ON DELETE CASCADE,
            amount REAL NOT NULL CHECK(amount > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(transaction_id, sales_invoice_id)
        );

        CREATE TABLE IF NOT EXISTS customer_account_adjustments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            adjustment_number TEXT NOT NULL UNIQUE,
            adjustment_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            customer_id INTEGER NOT NULL REFERENCES partners(id),
            adjustment_type TEXT NOT NULL CHECK(
                adjustment_type IN ('debit', 'credit')
            ),
            amount REAL NOT NULL CHECK(amount > 0),
            status TEXT NOT NULL DEFAULT 'posted' CHECK(
                status IN ('draft', 'posted', 'cancelled')
            ),
            notes TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_payment_allocations_transaction
        ON payment_allocations(transaction_id, id);
        CREATE INDEX IF NOT EXISTS idx_payment_allocations_invoice
        ON payment_allocations(sales_invoice_id, id);
        CREATE INDEX IF NOT EXISTS idx_customer_adjustments_customer
        ON customer_account_adjustments(customer_id, adjustment_date, id);
        CREATE INDEX IF NOT EXISTS idx_weight_cards_invoice
        ON sales_weight_cards(sales_invoice_id, id);

        CREATE TRIGGER IF NOT EXISTS trg_weight_invoice_sale_date
        AFTER INSERT ON sales_invoices
        WHEN NEW.invoice_type = 'weight'
        BEGIN
            UPDATE sales_invoices
            SET invoice_date = COALESCE(
                (
                    SELECT wc.card_date
                    FROM sales_weight_cards wc
                    WHERE wc.sales_order_id = NEW.sales_order_id
                    ORDER BY wc.id
                    LIMIT 1
                ),
                NEW.invoice_date
            )
            WHERE id = NEW.id;
        END;
        """
    )

    connection.execute(
        """
        UPDATE sales_invoices
        SET invoice_type = CASE
            WHEN EXISTS (
                SELECT 1 FROM sales_orders so
                WHERE so.id = sales_invoices.sales_order_id
                  AND so.billing_method = 'weight'
            ) THEN 'weight'
            ELSE 'standard'
        END
        WHERE invoice_type IS NULL
           OR TRIM(invoice_type) = ''
           OR invoice_type = 'standard'
        """
    )
    connection.execute(
        """
        UPDATE sales_invoices
        SET invoice_date = COALESCE(
            (
                SELECT wc.card_date
                FROM sales_weight_cards wc
                WHERE wc.sales_order_id = sales_invoices.sales_order_id
                ORDER BY wc.id
                LIMIT 1
            ),
            invoice_date
        )
        WHERE invoice_type = 'weight'
        """
    )
    connection.execute(
        """
        UPDATE sales_invoices
        SET net_total = total
        WHERE ABS(net_total) < 0.0000001 AND ABS(total) >= 0.0000001
        """
    )
    connection.execute(
        """
        UPDATE sales_weight_cards
        SET weight_mode = 'total_card', pricing_mode = 'uniform',
            net_amount = CASE
                WHEN ABS(net_amount) < 0.0000001 THEN total_amount
                ELSE net_amount
            END
        WHERE weight_mode IS NULL OR TRIM(weight_mode) = ''
           OR pricing_mode IS NULL OR TRIM(pricing_mode) = ''
           OR ABS(net_amount) < 0.0000001
        """
    )
    connection.execute(
        """
        UPDATE sales_weight_card_lines
        SET actual_weight_kg = allocated_weight_kg,
            price_per_kg = CASE
                WHEN allocated_weight_kg > 0
                THEN line_total / allocated_weight_kg
                ELSE 0
            END
        WHERE actual_weight_kg <= 0
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO payment_allocations(
            transaction_id, sales_invoice_id, amount
        )
        SELECT id, sales_invoice_id, amount
        FROM payment_transactions
        WHERE transaction_type = 'customer_receipt'
          AND sales_invoice_id IS NOT NULL
          AND amount > 0
        """
    )
    connection.execute(
        """
        UPDATE sales_weight_cards
        SET sales_invoice_id = (
            SELECT si.id FROM sales_invoices si
            WHERE si.sales_order_id = sales_weight_cards.sales_order_id
              AND si.status <> 'cancelled'
        )
        WHERE sales_invoice_id IS NULL
        """
    )

    connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    connection.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        ("db_version", DATABASE_VERSION),
    )


__all__ = [
    "DATABASE_VERSION",
    "SCHEMA_VERSION",
    "ensure_sales_finance_v10_schema",
]
