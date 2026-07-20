from app.database.connection import Database
from app.services.inventory_costing_service import InventoryCostingService
from app.services.payment_service import post_order_payment


class SalesRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.costing_service = InventoryCostingService()

    def list_orders(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT so.id, so.order_number, so.order_date, so.status,
                   p.name AS customer_name, w.name AS warehouse_name,
                   COUNT(sol.id) AS line_count,
                   COALESCE(GROUP_CONCAT(product.name, '، '), '') AS product_summary,
                   COALESCE(SUM(sol.line_total), 0) AS total,
                   COALESCE((
                       SELECT SUM(pt.amount) FROM payment_transactions pt
                       WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id
                   ), 0) AS paid
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            LEFT JOIN sales_order_lines sol ON sol.sales_order_id = so.id
            LEFT JOIN products product ON product.id = sol.product_id
            GROUP BY so.id, so.order_number, so.order_date, so.status,
                     p.name, w.name
            ORDER BY so.id DESC
            """
        )
        result = []
        for row in rows:
            item = dict(row)
            item["remaining"] = float(item["total"]) - float(item["paid"])
            result.append(item)
        return result

    def get_order_details(self, order_id: int) -> dict:
        order = self.database.fetch_one(
            """
            SELECT so.id, so.order_number, so.order_date, so.status,
                   so.notes, p.name AS customer_name, w.name AS warehouse_name,
                   COALESCE((
                       SELECT SUM(pt.amount) FROM payment_transactions pt
                       WHERE pt.reference_type = 'sale' AND pt.reference_id = so.id
                   ), 0) AS paid
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            WHERE so.id = ?
            """,
            (order_id,),
        )
        if order is None:
            raise ValueError("أمر البيع غير موجود")
        lines = self.database.fetch_all(
            """
            SELECT sol.id, product.code, product.name, sol.quantity,
                   sol.unit, sol.unit_price, sol.line_total
            FROM sales_order_lines sol
            JOIN products product ON product.id = sol.product_id
            WHERE sol.sales_order_id = ?
            ORDER BY sol.id
            """,
            (order_id,),
        )
        result = dict(order)
        result["lines"] = [dict(line) for line in lines]
        result["total"] = sum(float(line["line_total"]) for line in lines)
        result["remaining"] = float(result["total"]) - float(result["paid"])
        return result

    def get_default_warehouse_id(self) -> int:
        warehouse = self.database.fetch_one(
            "SELECT id FROM warehouses WHERE code = 'MAIN' AND is_active = 1 LIMIT 1"
        )
        if warehouse is None:
            raise ValueError("مخزن المصنع غير موجود")
        return int(warehouse["id"])

    def get_available_quantity(self, product_id: int, warehouse_id: int | None = None) -> float:
        warehouse_id = warehouse_id or self.get_default_warehouse_id()
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
        return self.create_order_with_lines(
            customer_id=customer_id,
            warehouse_id=self.get_default_warehouse_id(),
            lines=[
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                }
            ],
        )

    def create_order_with_lines(
        self,
        *,
        customer_id: int,
        warehouse_id: int | None = None,
        lines: list[dict],
        notes: str = "",
        paid_amount: float = 0,
    ) -> int:
        if not lines:
            raise ValueError("أضف بندًا واحدًا على الأقل")
        if paid_amount < 0:
            raise ValueError("المدفوع لا يمكن أن يكون سالبًا")

        normalized_lines: list[dict] = []
        for line_number, line in enumerate(lines, start=1):
            product_id = int(line["product_id"])
            quantity = float(line["quantity"])
            unit = str(line.get("unit", "")).strip() or "قطعة"
            unit_price = float(line.get("unit_price", 0))
            if quantity <= 0:
                raise ValueError(f"كمية البند رقم {line_number} يجب أن تكون أكبر من صفر")
            if unit_price < 0:
                raise ValueError(f"سعر البند رقم {line_number} لا يمكن أن يكون سالبًا")
            normalized_lines.append(
                {
                    "product_id": product_id,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "line_total": quantity * unit_price,
                }
            )

        order_total = sum(float(line["line_total"]) for line in normalized_lines)
        if paid_amount - order_total > 0.000001:
            raise ValueError("المدفوع لا يمكن أن يكون أكبر من إجمالي الأمر")

        with self.database.session(immediate=True) as connection:
            customer = connection.execute(
                """
                SELECT id FROM partners
                WHERE id = ? AND partner_type = 'customer' AND is_active = 1
                """,
                (customer_id,),
            ).fetchone()
            if customer is None:
                raise ValueError("العميل غير موجود أو غير نشط")
            warehouse_id = self.get_default_warehouse_id()
            next_id = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM sales_orders"
            ).fetchone()["next_id"]
            order_number = f"SO{int(next_id):05d}"
            cursor = connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, status, notes
                )
                VALUES (?, ?, ?, 'draft', ?)
                """,
                (order_number, customer_id, warehouse_id, notes.strip()),
            )
            order_id = int(cursor.lastrowid)
            for line in normalized_lines:
                connection.execute(
                    """
                    INSERT INTO sales_order_lines(
                        sales_order_id, product_id, quantity,
                        unit, unit_price, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        line["product_id"],
                        line["quantity"],
                        line["unit"],
                        line["unit_price"],
                        line["line_total"],
                    ),
                )
            if paid_amount > 0:
                post_order_payment(
                    connection,
                    transaction_type="customer_receipt",
                    partner_id=customer_id,
                    amount=paid_amount,
                    reference_type="sale",
                    reference_id=order_id,
                    notes=f"تحصيل عند إنشاء أمر البيع {order_number}",
                )
            return order_id

    def deliver_order(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT * FROM sales_orders WHERE id = ?", (order_id,)
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
                "UPDATE sales_orders SET status = 'delivered' WHERE id = ?", (order_id,)
            )
