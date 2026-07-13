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
        "inventory_cost_allocations",
        "manufacturing_recipes",
        "manufacturing_recipe_outputs",
        "manufacturing_recipe_components",
        "manufacturing_orders",
        "manufacturing_order_outputs",
        "manufacturing_order_materials",
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


def test_fifo_migration_backfills_historical_outbound_cost() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    from app.database.migrations import INITIAL_SCHEMA_SQL

    connection.executescript(INITIAL_SCHEMA_SQL)
    connection.execute("PRAGMA user_version = 3")
    warehouse_id = connection.execute(
        "INSERT INTO warehouses(code, name) VALUES ('MAIN', 'المصنع')"
    ).lastrowid
    product_id = connection.execute(
        """
        INSERT INTO products(code, name, product_type, unit)
        VALUES ('P-1', 'ماسورة', 'finished_good', 'قطعة')
        """
    ).lastrowid
    source_move_id = connection.execute(
        """
        INSERT INTO inventory_moves(
            product_id, warehouse_id, quantity_in, unit_cost, reference_type
        )
        VALUES (?, ?, 10, 5, 'adjustment')
        """,
        (product_id, warehouse_id),
    ).lastrowid
    outbound_move_id = connection.execute(
        """
        INSERT INTO inventory_moves(
            product_id, warehouse_id, quantity_out, unit_cost, reference_type
        )
        VALUES (?, ?, 6, 100, 'sale')
        """,
        (product_id, warehouse_id),
    ).lastrowid

    run_migrations(connection)

    allocation = connection.execute(
        """
        SELECT source_move_id, quantity, unit_cost
        FROM inventory_cost_allocations
        WHERE outbound_move_id = ?
        """,
        (outbound_move_id,),
    ).fetchone()
    assert allocation is not None
    assert allocation["source_move_id"] == source_move_id
    assert allocation["quantity"] == 6
    assert allocation["unit_cost"] == 5
    corrected_cost = connection.execute(
        "SELECT unit_cost FROM inventory_moves WHERE id = ?",
        (outbound_move_id,),
    ).fetchone()[0]
    assert corrected_cost == 5
