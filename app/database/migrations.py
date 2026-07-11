from collections.abc import Callable
from sqlite3 import Connection

DATABASE_VERSION = "0.6.0"
LATEST_SCHEMA_VERSION = 6


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


ACCOUNTING_SQL = """
CREATE TABLE IF NOT EXISTS payment_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_number TEXT NOT NULL UNIQUE,
    transaction_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    transaction_type TEXT NOT NULL CHECK(
        transaction_type IN ('customer_receipt', 'supplier_payment')
    ),
    partner_id INTEGER NOT NULL REFERENCES partners(id),
    amount REAL NOT NULL CHECK(amount > 0),
    payment_method TEXT NOT NULL DEFAULT 'cash',
    reference_type TEXT CHECK(reference_type IN ('sale', 'purchase') OR reference_type IS NULL),
    reference_id INTEGER,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_payments_partner
ON payment_transactions(partner_id, transaction_date, id);

CREATE INDEX IF NOT EXISTS idx_payments_reference
ON payment_transactions(reference_type, reference_id);

CREATE INDEX IF NOT EXISTS idx_payments_type
ON payment_transactions(transaction_type, transaction_date);
"""


INVOICES_SQL = """
CREATE TABLE IF NOT EXISTS sales_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE,
    sales_order_id INTEGER NOT NULL UNIQUE REFERENCES sales_orders(id),
    customer_id INTEGER NOT NULL REFERENCES partners(id),
    invoice_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'posted', 'cancelled')),
    total REAL NOT NULL DEFAULT 0,
    notes TEXT,
    posted_at TEXT,
    cancelled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS purchase_invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE,
    purchase_order_id INTEGER NOT NULL UNIQUE REFERENCES purchase_orders(id),
    supplier_id INTEGER NOT NULL REFERENCES partners(id),
    invoice_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft', 'posted', 'cancelled')),
    total REAL NOT NULL DEFAULT 0,
    notes TEXT,
    posted_at TEXT,
    cancelled_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sales_invoices_customer
ON sales_invoices(customer_id, invoice_date, id);
CREATE INDEX IF NOT EXISTS idx_purchase_invoices_supplier
ON purchase_invoices(supplier_id, invoice_date, id);
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


def _migration_005_accounting_and_single_warehouse(connection: Connection) -> None:
    connection.executescript(ACCOUNTING_SQL)
    connection.execute(
        "INSERT OR IGNORE INTO warehouses(code, name, is_active) VALUES ('MAIN', 'المصنع', 1)"
    )
    main_row = connection.execute(
        "SELECT id FROM warehouses WHERE code = 'MAIN'"
    ).fetchone()
    main_id = int(main_row[0])
    connection.execute(
        "UPDATE warehouses SET name = 'المصنع', is_active = 1 WHERE id = ?",
        (main_id,),
    )
    connection.execute("UPDATE purchase_orders SET warehouse_id = ?", (main_id,))
    connection.execute("UPDATE sales_orders SET warehouse_id = ?", (main_id,))
    connection.execute("UPDATE inventory_moves SET warehouse_id = ?", (main_id,))
    connection.execute("UPDATE warehouses SET is_active = 0 WHERE id <> ?", (main_id,))


def _migration_006_invoices(connection: Connection) -> None:
    connection.executescript(INVOICES_SQL)
    if not _column_exists(connection, "payment_transactions", "sales_invoice_id"):
        connection.execute(
            "ALTER TABLE payment_transactions ADD COLUMN sales_invoice_id INTEGER REFERENCES sales_invoices(id)"
        )
    if not _column_exists(connection, "payment_transactions", "purchase_invoice_id"):
        connection.execute(
            "ALTER TABLE payment_transactions ADD COLUMN purchase_invoice_id INTEGER REFERENCES purchase_invoices(id)"
        )

    sales_orders = connection.execute(
        """
        SELECT so.id, so.customer_id, so.order_date, so.status, so.notes,
               COALESCE(SUM(sol.line_total), 0) AS total
        FROM sales_orders so
        LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
        GROUP BY so.id, so.customer_id, so.order_date, so.status, so.notes
        ORDER BY so.id
        """
    ).fetchall()
    for order in sales_orders:
        status = "posted" if str(order[3]) == "delivered" else "draft"
        connection.execute(
            """
            INSERT OR IGNORE INTO sales_invoices(
                invoice_number, sales_order_id, customer_id, invoice_date,
                status, total, notes, posted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'posted' THEN ? ELSE NULL END)
            """,
            (
                f"SI{int(order[0]):05d}", order[0], order[1], order[2], status,
                float(order[5]), order[4] or "", status, order[2],
            ),
        )

    purchase_orders = connection.execute(
        """
        SELECT po.id, po.supplier_id, po.order_date, po.status, po.notes,
               COALESCE(SUM(pol.line_total), 0) AS total
        FROM purchase_orders po
        LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
        GROUP BY po.id, po.supplier_id, po.order_date, po.status, po.notes
        ORDER BY po.id
        """
    ).fetchall()
    for order in purchase_orders:
        status = "posted" if str(order[3]) == "received" else "draft"
        connection.execute(
            """
            INSERT OR IGNORE INTO purchase_invoices(
                invoice_number, purchase_order_id, supplier_id, invoice_date,
                status, total, notes, posted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CASE WHEN ? = 'posted' THEN ? ELSE NULL END)
            """,
            (
                f"PI{int(order[0]):05d}", order[0], order[1], order[2], status,
                float(order[5]), order[4] or "", status, order[2],
            ),
        )

    connection.execute(
        """
        UPDATE payment_transactions
        SET sales_invoice_id = (
            SELECT si.id FROM sales_invoices si
            WHERE si.sales_order_id = payment_transactions.reference_id
        )
        WHERE reference_type = 'sale' AND sales_invoice_id IS NULL
        """
    )
    connection.execute(
        """
        UPDATE payment_transactions
        SET purchase_invoice_id = (
            SELECT pi.id FROM purchase_invoices pi
            WHERE pi.purchase_order_id = payment_transactions.reference_id
        )
        WHERE reference_type = 'purchase' AND purchase_invoice_id IS NULL
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_payments_sales_invoice ON payment_transactions(sales_invoice_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_payments_purchase_invoice ON payment_transactions(purchase_invoice_id)"
    )


MIGRATIONS: tuple[tuple[int, Callable[[Connection], None]], ...] = (
    (1, _migration_001_initial_schema),
    (2, _migration_002_inventory_partner_link),
    (3, _migration_003_indexes),
    (4, _migration_004_fifo_cost_allocations),
    (5, _migration_005_accounting_and_single_warehouse),
    (6, _migration_006_invoices),
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
