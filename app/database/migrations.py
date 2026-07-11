from collections.abc import Callable
from sqlite3 import Connection


DATABASE_VERSION = "0.3.0"
LATEST_SCHEMA_VERSION = 3


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


MIGRATIONS: tuple[tuple[int, Callable[[Connection], None]], ...] = (
    (1, _migration_001_initial_schema),
    (2, _migration_002_inventory_partner_link),
    (3, _migration_003_indexes),
)


def run_migrations(connection: Connection) -> None:
    current_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current_version > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            "قاعدة البيانات أحدث من إصدار البرنامج الحالي. حدّث البرنامج قبل فتحها."
        )

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
