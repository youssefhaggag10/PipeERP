import os

from app.database.completion_summary_schema import ensure_completion_summary_schema
from app.database.connection import Database
from app.database.migrations import LATEST_SCHEMA_VERSION, run_migrations
from app.database.sales_finance_v10_schema import (
    SCHEMA_VERSION,
    ensure_sales_finance_v10_schema,
)
from app.security.passwords import hash_password


def initialize_database(database: Database) -> None:
    with database.session() as connection:
        current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                "قاعدة البيانات أحدث من إصدار البرنامج الحالي. حدّث البرنامج قبل فتحها."
            )
        if current_version <= LATEST_SCHEMA_VERSION:
            run_migrations(connection)
        ensure_sales_finance_v10_schema(connection)
        ensure_completion_summary_schema(connection)
        connection.execute(
            "INSERT OR IGNORE INTO warehouses(code, name) VALUES (?, ?)",
            ("MAIN", "المصنع"),
        )
        connection.execute(
            "UPDATE warehouses SET name = ? WHERE code = ?",
            ("المصنع", "MAIN"),
        )

        user_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        initial_password = os.environ.get("PIPEERP_ADMIN_PASSWORD", "").strip()
        if user_count == 0 and initial_password:
            connection.execute(
                """
                INSERT INTO users(username, password_hash, full_name, role)
                VALUES (?, ?, ?, ?)
                """,
                ("admin", hash_password(initial_password), "مدير النظام", "admin"),
            )
