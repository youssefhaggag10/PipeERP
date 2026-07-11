from app.database.connection import Database
from app.services.inventory_costing_service import InventoryCostingService


class SalesRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.costing_service = InventoryCostingService()

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
                """
                SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS qty
                FROM inventory_moves
                WHERE product_id = ?
                """,
                (product_id,),
            )
        else:
            row = self.database.fetch_one(
                """
                SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS qty
                FROM inventory_moves
                WHERE product_id = ? AND warehouse_id = ?
                """,
                (product_id, warehouse_id),
            )
        return float(row["qty"] if row is not None else 0)

    def create_order(
        self, customer_id: int, product_id: int, quantity: float, unit: str, unit_price: float
    ) -> int:
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")
        if unit_price < 0:
            raise ValueError("سعر الوحدة لا يمكن أن يكون سالبًا")
        warehouse = self.database.fetch_one(
            "SELECT id FROM warehouses WHERE is_active = 1 ORDER BY id LIMIT 1"
        )
        if warehouse is None:
            raise ValueError("لا يوجد مخزن")
        with self.database.session() as connection:
            next_id = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sales_orders"
            ).fetchone()["next_id"]
            order_number = f"SO{int(next_id):05d}"
            cursor = connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, status
                )
                VALUES (?, ?, ?, 'draft')
                """,
                (order_number, customer_id, warehouse["id"]),
            )
            order_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT INTO sales_order_lines(
                    sales_order_id, product_id, quantity,
                    unit, unit_price, line_total
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, product_id, quantity, unit, unit_price, quantity * unit_price),
            )
            return order_id

    def deliver_order(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT * FROM sales_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("أمر البيع غير موجود")
            if order["status"] == "delivered":
                return
            lines = connection.execute(
                "SELECT * FROM sales_order_lines WHERE sales_order_id = ? ORDER BY id",
                (order_id,),
            ).fetchall()
            if not lines:
                raise ValueError("أمر البيع لا يحتوي على بنود")

            for line in lines:
                self.costing_service.post_issue(
                    connection,
                    product_id=int(line["product_id"]),
                    warehouse_id=int(order["warehouse_id"]),
                    quantity=float(line["quantity"]),
                    reference_type="sale",
                    reference_id=order_id,
                    partner_id=int(order["customer_id"]),
                    notes=order["order_number"],
                )
            connection.execute(
                "UPDATE sales_orders SET status = 'delivered' WHERE id = ?",
                (order_id,),
            )
