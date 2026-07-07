from app.database.connection import Database


class ProductRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_products(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT id, code, name, product_type, unit, min_stock, track_lots, is_active
            FROM products
            ORDER BY id DESC
            """
        )
        return [dict(row) for row in rows]

    def create_product(self, data: dict) -> int:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit, min_stock, track_lots)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    data["code"],
                    data["name"],
                    data["product_type"],
                    data.get("unit", "كجم"),
                    float(data.get("min_stock", 0) or 0),
                    int(bool(data.get("track_lots", True))),
                ),
            )
            return int(cursor.lastrowid)

    def delete_product(self, product_id: int) -> None:
        with self.database.session() as connection:
            connection.execute("DELETE FROM products WHERE id = ?", (product_id,))
