from app.database.connection import Database


class ProductRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_products(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT id, code, name, product_type, unit, min_stock, track_lots,
                   standard_weight_kg, is_active
            FROM products
            WHERE is_active = 1
            ORDER BY id DESC
            """
        )
        return [dict(row) for row in rows]

    def create_product(self, data: dict) -> int:
        with self.database.session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, min_stock, track_lots,
                    standard_weight_kg
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    data["code"],
                    data["name"],
                    data["product_type"],
                    data.get("unit", "كجم"),
                    float(data.get("min_stock", 0) or 0),
                    int(bool(data.get("track_lots", True))),
                    float(data.get("standard_weight_kg", 0) or 0),
                ),
            )
            return int(cursor.lastrowid)

    def delete_product(self, product_id: int) -> None:
        with self.database.session() as connection:
            connection.execute(
                "UPDATE products SET is_active = 0 WHERE id = ?",
                (product_id,),
            )

    def count_by_type(self) -> dict:
        rows = self.database.fetch_all(
            """
            SELECT product_type, COUNT(*) AS count
            FROM products
            WHERE is_active = 1
            GROUP BY product_type
            """
        )
        result = {
            "raw_material": 0,
            "finished_good": 0,
            "waste": 0,
            "service": 0,
            "spare_part": 0,
        }
        for row in rows:
            result[row["product_type"]] = row["count"]
        result["total"] = sum(result.values())
        return result
