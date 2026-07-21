import os

from app.database.completion_summary_schema import ensure_completion_summary_schema
from app.database.connection import Database
from app.database.migrations import run_migrations
from app.security.passwords import hash_password


def initialize_database(database: Database) -> None:
    with database.session() as connection:
        run_migrations(connection)
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
