from __future__ import annotations

from sqlite3 import Connection

SCHEMA_VERSION = 11
DATABASE_VERSION = "0.11.0"


def ensure_partner_opening_balance_schema(connection: Connection) -> None:
    """Create auditable partner opening balances and migrate legacy values."""

    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            "قاعدة البيانات أحدث من إصدار البرنامج الحالي. حدّث البرنامج قبل فتحها."
        )

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_permissions(
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            permission_code TEXT NOT NULL,
            allowed INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(user_id, permission_code)
        );

        CREATE INDEX IF NOT EXISTS idx_user_permissions_user
        ON user_permissions(user_id, allowed);

        CREATE TABLE IF NOT EXISTS partner_opening_balance_entries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_number TEXT NOT NULL UNIQUE,
            entry_date TEXT NOT NULL,
            partner_id INTEGER NOT NULL REFERENCES partners(id),
            nature TEXT NOT NULL CHECK(nature IN ('debit', 'credit')),
            amount REAL NOT NULL CHECK(amount > 0),
            source TEXT NOT NULL DEFAULT 'manual' CHECK(
                source IN ('manual', 'legacy', 'reversal')
            ),
            reversal_of_id INTEGER UNIQUE
                REFERENCES partner_opening_balance_entries(id),
            notes TEXT NOT NULL DEFAULT '',
            created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_by_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_partner_opening_entries_partner
        ON partner_opening_balance_entries(partner_id, entry_date, id);

        CREATE INDEX IF NOT EXISTS idx_partner_opening_entries_reversal
        ON partner_opening_balance_entries(reversal_of_id);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_partner_opening_legacy
        ON partner_opening_balance_entries(partner_id)
        WHERE source = 'legacy';
        """
    )

    if current_version < SCHEMA_VERSION:
        connection.execute(
            """
            INSERT OR IGNORE INTO partner_opening_balance_entries(
                entry_number, entry_date, partner_id, nature, amount,
                source, notes, created_by_name
            )
            SELECT
                printf('OB-LGC-%06d', p.id),
                substr(COALESCE(p.created_at, CURRENT_TIMESTAMP), 1, 10),
                p.id,
                CASE
                    WHEN p.partner_type = 'customer' AND p.opening_balance >= 0
                        THEN 'debit'
                    WHEN p.partner_type = 'customer' AND p.opening_balance < 0
                        THEN 'credit'
                    WHEN p.partner_type = 'supplier' AND p.opening_balance >= 0
                        THEN 'credit'
                    ELSE 'debit'
                END,
                ABS(p.opening_balance),
                'legacy',
                'ترحيل تلقائي للرصيد الافتتاحي من الإصدار السابق',
                'ترحيل النظام'
            FROM partners p
            WHERE ABS(p.opening_balance) > 0.0000001
            """
        )
        connection.execute(
            """
            UPDATE partners
            SET opening_balance = 0
            WHERE ABS(opening_balance) > 0.0000001
              AND EXISTS (
                  SELECT 1
                  FROM partner_opening_balance_entries entry
                  WHERE entry.partner_id = partners.id
                    AND entry.source = 'legacy'
              )
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
    "ensure_partner_opening_balance_schema",
]
