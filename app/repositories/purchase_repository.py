from app.database.connection import Database


class PurchaseRepository:
    def __init__(self, database: Database) -> None:
        self.database = database

    def list_orders(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT po.id, po.order_number, po.order_date, po.status,
                   p.name AS supplier_name, w.name AS warehouse_name,
                   COUNT(pol.id) AS line_count,
                   COALESCE(GROUP_CONCAT(product.name, '، '), '') AS product_summary,
                   COALESCE(SUM(pol.line_total), 0) AS total
            FROM purchase_orders po
            JOIN partners p ON p.id = po.supplier_id
            JOIN warehouses w ON w.id = po.warehouse_id
            LEFT JOIN purchase_order_lines pol ON pol.purchase_order_id = po.id
            LEFT JOIN products product ON product.id = pol.product_id
            GROUP BY po.id, po.order_number, po.order_date, po.status,
                     p.name, w.name
            ORDER BY po.id DESC
            """
        )
        return [dict(row) for row in rows]

    def get_order_details(self, order_id: int) -> dict:
        order = self.database.fetch_one(
            """
            SELECT po.id, po.order_number, po.order_date, po.status,
                   po.notes, p.name AS supplier_name, w.name AS warehouse_name
            FROM purchase_orders po
            JOIN partners p ON p.id = po.supplier_id
            JOIN warehouses w ON w.id = po.warehouse_id
            WHERE po.id = ?
            """,
            (order_id,),
        )
        if order is None:
            raise ValueError("أمر الشراء غير موجود")
        lines = self.database.fetch_all(
            """
            SELECT pol.id, product.code, product.name, pol.lot_number,
                   pol.quantity, pol.unit, pol.unit_price, pol.line_total
            FROM purchase_order_lines pol
            JOIN products product ON product.id = pol.product_id
            WHERE pol.purchase_order_id = ?
            ORDER BY pol.id
            """,
            (order_id,),
        )
        result = dict(order)
        result["lines"] = [dict(line) for line in lines]
        result["total"] = sum(float(line["line_total"]) for line in lines)
        return result

    def get_default_warehouse_id(self) -> int:
        warehouse = self.database.fetch_one(
            "SELECT id FROM warehouses WHERE is_active = 1 ORDER BY id LIMIT 1"
        )
        if warehouse is None:
            raise ValueError("لا يوجد مخزن افتراضي")
        return int(warehouse["id"])

    def create_order(
        self,
        supplier_id: int,
        product_id: int,
        lot_number: str,
        quantity: float,
        unit: str,
        unit_price: float,
    ) -> int:
        if quantity <= 0:
            raise ValueError("الكمية يجب أن تكون أكبر من صفر")
        if unit_price < 0:
            raise ValueError("سعر الوحدة لا يمكن أن يكون سالبًا")
        if not lot_number.strip():
            raise ValueError("رقم الدفعة مطلوب")
        return self.create_order_with_lines(
            supplier_id=supplier_id,
            warehouse_id=self.get_default_warehouse_id(),
            lines=[
                {
                    "product_id": product_id,
                    "lot_number": lot_number,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                }
            ],
        )

    def create_order_with_lines(
        self,
        *,
        supplier_id: int,
        warehouse_id: int,
        lines: list[dict],
        notes: str = "",
    ) -> int:
        if not lines:
            raise ValueError("أضف بندًا واحدًا على الأقل")

        normalized_lines: list[dict] = []
        for line_number, line in enumerate(lines, start=1):
            product_id = int(line["product_id"])
            lot_number = str(line.get("lot_number", "")).strip()
            quantity = float(line["quantity"])
            unit = str(line.get("unit", "")).strip() or "كجم"
            unit_price = float(line.get("unit_price", 0))
            if quantity <= 0:
                raise ValueError(f"كمية البند رقم {line_number} يجب أن تكون أكبر من صفر")
            if unit_price < 0:
                raise ValueError(f"سعر البند رقم {line_number} لا يمكن أن يكون سالبًا")
            if not lot_number:
                raise ValueError(f"رقم الدفعة مطلوب في البند رقم {line_number}")
            normalized_lines.append(
                {
                    "product_id": product_id,
                    "lot_number": lot_number,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "line_total": quantity * unit_price,
                }
            )

        with self.database.session(immediate=True) as connection:
            supplier = connection.execute(
                """
                SELECT id FROM partners
                WHERE id = ? AND partner_type = 'supplier' AND is_active = 1
                """,
                (supplier_id,),
            ).fetchone()
            warehouse = connection.execute(
                "SELECT id FROM warehouses WHERE id = ? AND is_active = 1",
                (warehouse_id,),
            ).fetchone()
            if supplier is None:
                raise ValueError("المورد غير موجود أو غير نشط")
            if warehouse is None:
                raise ValueError("المخزن غير موجود أو غير نشط")
            next_id = connection.execute(
                "SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM purchase_orders"
            ).fetchone()["next_id"]
            order_number = f"PO{int(next_id):05d}"
            cursor = connection.execute(
                """
                INSERT INTO purchase_orders(
                    order_number, supplier_id, warehouse_id, status, notes
                )
                VALUES (?, ?, ?, 'draft', ?)
                """,
                (order_number, supplier_id, warehouse_id, notes.strip()),
            )
            order_id = int(cursor.lastrowid)
            for line in normalized_lines:
                connection.execute(
                    """
                    INSERT INTO purchase_order_lines(
                        purchase_order_id, product_id, lot_number, quantity,
                        unit, unit_price, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        line["product_id"],
                        line["lot_number"],
                        line["quantity"],
                        line["unit"],
                        line["unit_price"],
                        line["line_total"],
                    ),
                )
            return order_id

    def receive_order(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT * FROM purchase_orders WHERE id = ?",
                (order_id,),
            ).fetchone()
            if order is None:
                raise ValueError("أمر الشراء غير موجود")
            if order["status"] == "received":
                return
            lines = connection.execute(
                "SELECT * FROM purchase_order_lines WHERE purchase_order_id = ? ORDER BY id",
                (order_id,),
            ).fetchall()
            if not lines:
                raise ValueError("أمر الشراء لا يحتوي على بنود")

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
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in,
                        quantity_out, unit_cost, reference_type,
                        reference_id, partner_id, notes
                    )
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
            connection.execute(
                "UPDATE purchase_orders SET status = 'received' WHERE id = ?",
                (order_id,),
            )
