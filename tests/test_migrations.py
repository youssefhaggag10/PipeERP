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


def test_existing_inventory_moves_get_partner_link() -> None:
    connection = sqlite3.connect(":memory:")
    connection.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE inventory_moves (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            warehouse_id INTEGER NOT NULL,
            quantity_in REAL NOT NULL DEFAULT 0,
            quantity_out REAL NOT NULL DEFAULT 0,
            unit_cost REAL NOT NULL DEFAULT 0,
            reference_type TEXT NOT NULL
        );
        """
    )
    connection.execute("PRAGMA user_version = 1")

    run_migrations(connection)

    columns = {
        row[1] for row in connection.execute("PRAGMA table_info(inventory_moves)").fetchall()
    }
    assert "partner_id" in columns
