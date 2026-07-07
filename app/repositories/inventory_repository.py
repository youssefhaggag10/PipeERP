from app.database.connection import Database


class InventoryRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_stock_on_hand(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT
                p.id,
                p.code,
                p.name,
                p.product_type,
                p.unit,
                COALESCE(SUM(m.quantity_in - m.quantity_out), 0) AS quantity
            FROM products p
            LEFT JOIN inventory_moves m ON m.product_id = p.id
            WHERE p.is_active = 1
            GROUP BY p.id, p.code, p.name, p.product_type, p.unit
            ORDER BY p.id DESC
            """
        )
        return [dict(row) for row in rows]

    def total_quantity(self) -> float:
        row = self.database.fetch_one(
            "SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS quantity FROM inventory_moves"
        )
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
                SELECT product_id
                FROM inventory_moves
                GROUP BY product_id
                HAVING SUM(quantity_in - quantity_out) <> 0
            )
            """
        )
        return int(row["count"] if row is not None else 0)

    def post_adjustment(self, product_id: int, quantity: float, notes: str = "") -> None:
        if quantity == 0:
            return
        quantity_in = quantity if quantity > 0 else 0
        quantity_out = abs(quantity) if quantity < 0 else 0
        warehouse_row = self.database.fetch_one("SELECT id FROM warehouses ORDER BY id LIMIT 1")
        if warehouse_row is None:
            raise ValueError("لا يوجد مخزن افتراضي")
        with self.database.session() as connection:
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, quantity_out,
                    unit_cost, reference_type, notes
                )
                VALUES (?, ?, ?, ?, 0, 'adjustment', ?)
                """,
                (product_id, warehouse_row["id"], quantity_in, quantity_out, notes),
            )
