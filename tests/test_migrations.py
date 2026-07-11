import sqlite3

from app.database.migrations import LATEST_SCHEMA_VERSION, run_migrations


def test_migrations_create_complete_schema() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    run_migrations(connection)

    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "users",
        "settings",
        "warehouses",
        "partners",
        "products",
        "lots",
        "inventory_moves",
        "purchase_orders",
        "purchase_order_lines",
        "sales_orders",
        "sales_order_lines",
    }.issubset(tables)
    assert connection.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION


def test_migrations_are_idempotent() -> None:
    connection = sqlite3.connect(":memory:")

    run_migrations(connection)
    run_migrations(connection)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION
    version_rows = connection.execute(
        "SELECT value FROM settings WHERE key = 'db_version'"
    ).fetchall()
    assert len(version_rows) == 1
