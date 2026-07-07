from app.database.connection import Database


class SalesRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.ensure_schema()

    def ensure_schema(self) -> None:
        with self.database.session() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sales_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_number TEXT NOT NULL UNIQUE,
                    customer_id INTEGER NOT NULL REFERENCES partners(id),
                    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
                    order_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL DEFAULT 'draft',
                    notes TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sales_order_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sales_order_id INTEGER NOT NULL REFERENCES sales_orders(id),
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    quantity REAL NOT NULL,
                    unit TEXT NOT NULL,
                    unit_price REAL NOT NULL DEFAULT 0,
                    line_total REAL NOT NULL DEFAULT 0
                )
                """
            )

    def list_orders(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT so.id, so.order_number, so.order_date, so.status, p.name AS customer_name,
                   w.name AS warehouse_name,
                   COALESCE(SUM(sol.line_total), 0) AS total
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
            GROUP BY so.id, so.order_number, so.order_date, so.status, p.name, w.name
            ORDER BY so.id DESC
            """
        )
        return [dict(row) for row in rows]

    def get_available_quantity(self, product_id: int, warehouse_id: int | None = None) -> float:
        if warehouse_id is None:
            row = self.database.fetch_one(
                "SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS qty FROM inventory_moves WHERE product_id = ?",
                (product_id,),
            )
        else:
            row = self.database.fetch_one(
                "SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS qty FROM inventory_moves WHERE product_id = ? AND warehouse_id = ?",
                (product_id, warehouse_id),
            )
        return float(row["qty"] if row is not None else 0)

    def create_order(self, customer_id: int, product_id: int, quantity: float, unit: str, unit_price: float) -> int:
        warehouse = self.database.fetch_one("SELECT id FROM warehouses WHERE is_active = 1 ORDER BY id LIMIT 1")
        if warehouse is None:
            raise ValueError("لا يوجد مخزن")
        with self.database.session() as connection:
            next_id = connection.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sales_orders").fetchone()["next_id"]
            order_number = f"SO{int(next_id):05d}"
            cursor = connection.execute(
                "INSERT INTO sales_orders(order_number, customer_id, warehouse_id, status) VALUES (?, ?, ?, 'draft')",
                (order_number, customer_id, warehouse["id"]),
            )
            order_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO sales_order_lines(sales_order_id, product_id, quantity, unit, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, product_id, quantity, unit, unit_price, quantity * unit_price),
            )
            return order_id

    def deliver_order(self, order_id: int) -> None:
        order = self.database.fetch_one("SELECT * FROM sales_orders WHERE id = ?", (order_id,))
        if order is None:
            raise ValueError("أمر البيع غير موجود")
        if order["status"] == "delivered":
            return
        lines = self.database.fetch_all("SELECT * FROM sales_order_lines WHERE sales_order_id = ?", (order_id,))
        for line in lines:
            available_qty = self.get_available_quantity(int(line["product_id"]), int(order["warehouse_id"]))
            if available_qty < float(line["quantity"]):
                raise ValueError(f"الرصيد غير كافي. المتاح {available_qty} والمطلوب {line['quantity']}")
        with self.database.session() as connection:
            for line in lines:
                connection.execute(
                    """
                    INSERT INTO inventory_moves(product_id, warehouse_id, quantity_in, quantity_out, unit_cost, reference_type, reference_id, partner_id, notes)
                    VALUES (?, ?, 0, ?, ?, 'sale', ?, ?, ?)
                    """,
                    (line["product_id"], order["warehouse_id"], line["quantity"], line["unit_price"], order_id, order["customer_id"], order["order_number"]),
                )
            connection.execute("UPDATE sales_orders SET status = 'delivered' WHERE id = ?", (order_id,))
