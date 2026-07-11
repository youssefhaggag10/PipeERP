from collections.abc import Callable
from sqlite3 import Connection

DATABASE_VERSION = "0.4.0"
LATEST_SCHEMA_VERSION = 4


INITIAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'admin',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS partners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    partner_type TEXT NOT NULL,
    code TEXT UNIQUE,
    name TEXT NOT NULL,
    phone TEXT,
    address TEXT,
    opening_balance REAL NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    product_type TEXT NOT NULL,
    unit TEXT NOT NULL DEFAULT 'كجم',
    min_stock REAL NOT NULL DEFAULT 0,
    track_lots INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES products(id),
    lot_number TEXT NOT NULL,
    unit_cost REAL NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, lot_number)
);

CREATE TABLE IF NOT EXISTS inventory_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    move_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    lot_id INTEGER REFERENCES lots(id),
    quantity_in REAL NOT NULL DEFAULT 0,
    quantity_out REAL NOT NULL DEFAULT 0,
    unit_cost REAL NOT NULL DEFAULT 0,
    reference_type TEXT NOT NULL,
    reference_id INTEGER,
    partner_id INTEGER REFERENCES partners(id),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,
    supplier_id INTEGER NOT NULL REFERENCES partners(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    order_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    lot_number TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_number TEXT NOT NULL UNIQUE,
    customer_id INTEGER NOT NULL REFERENCES partners(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    order_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft',
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales_order_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sales_order_id INTEGER NOT NULL REFERENCES sales_orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL,
    unit TEXT NOT NULL,
    unit_price REAL NOT NULL DEFAULT 0,
    line_total REAL NOT NULL DEFAULT 0
);
"""


INDEXES_SQL = """
CREATE INDEX IF NOT EXISTS idx_inventory_moves_product
ON inventory_moves(product_id);

CREATE INDEX IF NOT EXISTS idx_inventory_moves_warehouse
ON inventory_moves(warehouse_id);

CREATE INDEX IF NOT EXISTS idx_inventory_moves_partner
ON inventory_moves(partner_id);

CREATE INDEX IF NOT EXISTS idx_inventory_moves_reference
ON inventory_moves(reference_type, reference_id);

CREATE INDEX IF NOT EXISTS idx_lots_product
ON lots(product_id);
"""


FIFO_COSTING_SQL = """
CREATE TABLE IF NOT EXISTS inventory_cost_allocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    outbound_move_id INTEGER NOT NULL REFERENCES inventory_moves(id),
    source_move_id INTEGER NOT NULL REFERENCES inventory_moves(id),
    quantity REAL NOT NULL CHECK(quantity > 0),
    unit_cost REAL NOT NULL CHECK(unit_cost >= 0),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(outbound_move_id, source_move_id)
);

CREATE INDEX IF NOT EXISTS idx_cost_allocations_outbound
ON inventory_cost_allocations(outbound_move_id);

CREATE INDEX IF NOT EXISTS idx_cost_allocations_source
ON inventory_cost_allocations(source_move_id);

CREATE INDEX IF NOT EXISTS idx_inventory_moves_fifo
ON inventory_moves(product_id, warehouse_id, move_date, id);
"""


def _column_exists(connection: Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _migration_001_initial_schema(connection: Connection) -> None:
    connection.executescript(INITIAL_SCHEMA_SQL)


def _migration_002_inventory_partner_link(connection: Connection) -> None:
    if not _column_exists(connection, "inventory_moves", "partner_id"):
        connection.execute(
            "ALTER TABLE inventory_moves ADD COLUMN partner_id INTEGER REFERENCES partners(id)"
        )


def _migration_003_indexes(connection: Connection) -> None:
    connection.executescript(INDEXES_SQL)


def _migration_004_fifo_cost_allocations(connection: Connection) -> None:
    connection.executescript(FIFO_COSTING_SQL)

    outbound_moves = connection.execute(
        """
        SELECT id, product_id, warehouse_id, quantity_out
        FROM inventory_moves
        WHERE quantity_out > 0
          AND NOT EXISTS (
              SELECT 1
              FROM inventory_cost_allocations a
              WHERE a.outbound_move_id = inventory_moves.id
          )
        ORDER BY move_date, id
        """
    ).fetchall()

    for outbound in outbound_moves:
        outbound_id = int(outbound[0])
        product_id = int(outbound[1])
        warehouse_id = int(outbound[2])
        remaining_to_allocate = float(outbound[3])
        allocated_value = 0.0
        sources = connection.execute(
            """
            SELECT source.id, source.unit_cost,
                   source.quantity_in - COALESCE(SUM(a.quantity), 0) AS remaining
            FROM inventory_moves source
            LEFT JOIN inventory_cost_allocations a ON a.source_move_id = source.id
            WHERE source.product_id = ?
              AND source.warehouse_id = ?
              AND source.quantity_in > 0
              AND source.id < ?
            GROUP BY source.id, source.unit_cost, source.quantity_in, source.move_date
            HAVING remaining > 0.0000001
            ORDER BY source.move_date, source.id
            """,
            (product_id, warehouse_id, outbound_id),
        ).fetchall()

        for source in sources:
            if remaining_to_allocate <= 0.0000001:
                break
            allocated_quantity = min(remaining_to_allocate, float(source[2]))
            unit_cost = float(source[1])
            connection.execute(
                """
                INSERT INTO inventory_cost_allocations(
                    outbound_move_id, source_move_id, quantity, unit_cost
                )
                VALUES (?, ?, ?, ?)
                """,
                (outbound_id, source[0], allocated_quantity, unit_cost),
            )
            allocated_value += allocated_quantity * unit_cost
            remaining_to_allocate -= allocated_quantity

        original_quantity = float(outbound[3])
        if remaining_to_allocate <= 0.0000001 and original_quantity > 0:
            connection.execute(
                "UPDATE inventory_moves SET unit_cost = ? WHERE id = ?",
                (allocated_value / original_quantity, outbound_id),
            )


MIGRATIONS: tuple[tuple[int, Callable[[Connection], None]], ...] = (
    (1, _migration_001_initial_schema),
    (2, _migration_002_inventory_partner_link),
    (3, _migration_003_indexes),
    (4, _migration_004_fifo_cost_allocations),
)


def run_migrations(connection: Connection) -> None:
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > LATEST_SCHEMA_VERSION:
        raise RuntimeError("قاعدة البيانات أحدث من إصدار البرنامج الحالي. حدّث البرنامج قبل فتحها.")

    for version, migration in MIGRATIONS:
        if version <= current_version:
            continue
        migration(connection)
        connection.execute(f"PRAGMA user_version = {version}")
        current_version = version

    connection.execute(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        ("db_version", DATABASE_VERSION),
    )
