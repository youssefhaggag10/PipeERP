from app.database.connection import Database


class WarehouseRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.ensure_defaults()

    def ensure_defaults(self) -> None:
        with self.database.session() as connection:
            connection.execute("INSERT OR IGNORE INTO warehouses(code, name) VALUES (?, ?)", ("MAIN", "المصنع"))
            connection.execute("UPDATE warehouses SET name = ? WHERE code = ?", ("المصنع", "MAIN"))

    def list_warehouses(self) -> list[dict]:
        rows = self.database.fetch_all("SELECT id, code, name, is_active FROM warehouses WHERE is_active = 1 ORDER BY id")
        return [dict(row) for row in rows]

    def create_warehouse(self, code: str, name: str) -> int:
        with self.database.session() as connection:
            cursor = connection.execute("INSERT INTO warehouses(code, name) VALUES (?, ?)", (code.strip(), name.strip()))
            return int(cursor.lastrowid)
