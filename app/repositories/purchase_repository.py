from app.database.connection import Database


class PurchaseRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_orders(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT po.id, po.order_number, po.order_date, po.status, p.name AS supplier_name,
                   COALESCE(SUM(pol.line_total), 0) AS total
            FROM purchase_orders po
            JOIN partners p ON p.id = po.supplier_id
            LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
            GROUP BY po.id, po.order_number, po.order_date, po.status, p.name
            ORDER BY po.id DESC
            """
        )
        return [dict(row) for row in rows]

    def create_order(self, supplier_id: int, product_id: int, lot_number: str, quantity: float, unit: str, unit_price: float) -> int:
        warehouse = self.database.fetch_one("SELECT id FROM warehouses ORDER BY id LIMIT 1")
        if warehouse is None:
            raise ValueError("لا يوجد مخزن افتراضي")
        with self.database.session() as connection:
            next_id = connection.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM purchase_orders").fetchone()["next_id"]
            order_number = f"PO{int(next_id):05d}"
            cursor = connection.execute(
                """
                INSERT INTO purchase_orders(order_number, supplier_id, warehouse_id, status)
                VALUES (?, ?, ?, 'draft')
                """,
                (order_number, supplier_id, warehouse["id"]),
            )
            order_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO purchase_order_lines(purchase_order_id, product_id, lot_number, quantity, unit, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, product_id, lot_number.strip(), quantity, unit, unit_price, quantity * unit_price),
            )
            return order_id

    def receive_order(self, order_id: int) -> None:
        order = self.database.fetch_one("SELECT * FROM purchase_orders WHERE id = ?", (order_id,))
        if order is None:
            raise ValueError("أمر الشراء غير موجود")
        if order["status"] == "received":
            return
        lines = self.database.fetch_all("SELECT * FROM purchase_order_lines WHERE purchase_order_id = ?", (order_id,))
        with self.database.session() as connection:
            for line in lines:
                lot = connection.execute(
                    "SELECT id FROM lots WHERE product_id = ? AND lot_number = ?",
                    (line["product_id"], line["lot_number"]),
                ).fetchone()
                if lot is None:
                    lot_cursor = connection.execute(
                        "INSERT INTO lots(product_id, lot_number, unit_cost) VALUES (?, ?, ?)",
                        (line["product_id"], line["lot_number"], line["unit_price"]),
                    )
                    lot_id = int(lot_cursor.lastrowid)
                else:
                    lot_id = int(lot["id"])
                connection.execute(
                    """
                    INSERT INTO inventory_moves(product_id, warehouse_id, lot_id, quantity_in, quantity_out, unit_cost, reference_type, reference_id, partner_id, notes)
                    VALUES (?, ?, ?, ?, 0, ?, 'purchase', ?, ?, ?)
                    """,
                    (
                        line["product_id"],
                        order["warehouse_id"],
                        lot_id,
                        line["quantity"],
                        line["unit_price"],
                        order_id,
                        order["supplier_id"],
                        order["order_number"],
                    ),
                )
            connection.execute("UPDATE purchase_orders SET status = 'received' WHERE id = ?", (order_id,))
