from app.database.connection import Database


class InventoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_stock_on_hand(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT p.id, p.code, p.name, p.product_type, p.unit, p.min_stock,
                   COALESCE(SUM(m.quantity_in - m.quantity_out), 0) AS quantity
            FROM products p
            LEFT JOIN inventory_moves m ON m.product_id = p.id
            WHERE p.is_active = 1
            GROUP BY p.id, p.code, p.name, p.product_type, p.unit, p.min_stock
            ORDER BY p.id DESC
            """
        )
        return [dict(row) for row in rows]

    def list_stock_card(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT m.move_date, p.code, p.name, p.product_type, w.name AS warehouse_name,
                   COALESCE(l.lot_number, '') AS lot_number,
                   m.quantity_in, m.quantity_out,
                   m.unit_cost, m.reference_type, m.reference_id,
                   COALESCE(pa.name, '') AS partner_name,
                   COALESCE(m.notes, '') AS notes
            FROM inventory_moves m
            JOIN products p ON p.id = m.product_id
            JOIN warehouses w ON w.id = m.warehouse_id
            LEFT JOIN lots l ON l.id = m.lot_id
            LEFT JOIN partners pa ON pa.id = m.partner_id
            ORDER BY m.id DESC
            """
        )
        return [dict(row) for row in rows]

    def total_quantity(self) -> float:
        row = self.database.fetch_one("SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS quantity FROM inventory_moves")
        return float(row["quantity"] if row is not None else 0)

    def total_quantity_by_type(self, product_type: str) -> float:
        row = self.database.fetch_one(
            """
            SELECT COALESCE(SUM(m.quantity_in - m.quantity_out), 0) AS quantity
            FROM inventory_moves m
            JOIN products p ON p.id = m.product_id
            WHERE p.product_type = ?
            """,
            (product_type,),
        )
        return float(row["quantity"] if row is not None else 0)

    def count_products_with_stock(self) -> int:
        row = self.database.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM (
                SELECT product_id FROM inventory_moves
                GROUP BY product_id
                HAVING SUM(quantity_in - quantity_out) <> 0
            )
            """
        )
        return int(row["count"] if row is not None else 0)

    def count_low_stock(self) -> int:
        row = self.database.fetch_one(
            """
            SELECT COUNT(*) AS count
            FROM (
                SELECT p.id, p.min_stock, COALESCE(SUM(m.quantity_in - quantity_out), 0) AS qty
                FROM products p
                LEFT JOIN inventory_moves m ON m.product_id = p.id
                WHERE p.is_active = 1 AND p.min_stock > 0
                GROUP BY p.id, p.min_stock
                HAVING qty < p.min_stock
            )
            """
        )
        return int(row["count"] if row is not None else 0)

    def get_default_warehouse_id(self) -> int:
        warehouse_row = self.database.fetch_one("SELECT id FROM warehouses WHERE is_active = 1 ORDER BY id LIMIT 1")
        if warehouse_row is None:
            warehouse_row = self.database.fetch_one("SELECT id FROM warehouses ORDER BY id LIMIT 1")
        if warehouse_row is None:
            raise ValueError("لا يوجد مخزن افتراضي")
        return int(warehouse_row["id"])

    def post_adjustment(self, product_id: int, quantity: float, notes: str = "") -> None:
        if quantity == 0:
            return
        quantity_in = quantity if quantity > 0 else 0
        quantity_out = abs(quantity) if quantity < 0 else 0
        warehouse_id = self.get_default_warehouse_id()
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO inventory_moves(product_id, warehouse_id, quantity_in, quantity_out, unit_cost, reference_type, notes)
                VALUES (?, ?, ?, ?, 0, 'adjustment', ?)
                """,
                (product_id, warehouse_id, quantity_in, quantity_out, notes),
            )
