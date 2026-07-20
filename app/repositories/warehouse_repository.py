from app.database.connection import Database


class WarehouseRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.ensure_defaults()

    def ensure_defaults(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO warehouses(code, name, is_active) VALUES (?, ?, 1)",
                ("MAIN", "المصنع"),
            )
            main = connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()
            main_id = int(main["id"])
            connection.execute(
                "UPDATE warehouses SET name = ?, is_active = 1 WHERE id = ?",
                ("المصنع", main_id),
            )
            connection.execute("UPDATE purchase_orders SET warehouse_id = ?", (main_id,))
            connection.execute("UPDATE sales_orders SET warehouse_id = ?", (main_id,))
            connection.execute("UPDATE inventory_moves SET warehouse_id = ?", (main_id,))
            connection.execute("UPDATE warehouses SET is_active = 0 WHERE id <> ?", (main_id,))

    def get_factory_warehouse(self) -> dict:
        row = self.database.fetch_one(
            "SELECT id, code, name, is_active FROM warehouses WHERE code = 'MAIN' LIMIT 1"
        )
        if row is None:
            raise ValueError("مخزن المصنع غير موجود")
        return dict(row)

    def list_warehouses(self) -> list[dict]:
        return [self.get_factory_warehouse()]

    def create_warehouse(self, code: str, name: str) -> int:
        raise ValueError("النظام مضبوط على مخزن واحد فقط باسم المصنع")
