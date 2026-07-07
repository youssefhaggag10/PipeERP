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
