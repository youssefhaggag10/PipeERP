from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.repositories.treasury_invoice_repository import TreasuryInvoiceRepository
from app.services.inventory_costing_service import InventoryCostingService
from app.services.invoice_service import payment_status

EPSILON = 0.000001


class ReturnInvoiceRepository(TreasuryInvoiceRepository):
    """Invoice returns linked to the original invoice and posted to inventory."""

    def __init__(self, database) -> None:
        super().__init__(database)
        self.costing_service = InventoryCostingService()
        self._ensure_return_schema()

    def _ensure_return_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS invoice_returns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    return_number TEXT NOT NULL UNIQUE,
                    invoice_type TEXT NOT NULL CHECK(invoice_type IN ('sales', 'purchase')),
                    invoice_id INTEGER NOT NULL,
                    return_date TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    total REAL NOT NULL CHECK(total > 0),
                    reason TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS invoice_return_lines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    return_id INTEGER NOT NULL REFERENCES invoice_returns(id),
                    order_line_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL REFERENCES products(id),
                    quantity REAL NOT NULL CHECK(quantity > 0),
                    unit TEXT NOT NULL,
                    unit_price REAL NOT NULL CHECK(unit_price >= 0),
                    line_total REAL NOT NULL CHECK(line_total >= 0)
                );

                CREATE INDEX IF NOT EXISTS idx_invoice_returns_invoice
                ON invoice_returns(invoice_type, invoice_id, return_date, id);

                CREATE INDEX IF NOT EXISTS idx_invoice_return_lines_return
                ON invoice_return_lines(return_id, order_line_id);
                """
            )

    def list_invoices(self, invoice_type: str) -> list[dict]:
        rows = super().list_invoices(invoice_type)
        for item in rows:
            returned = self._returned_total(invoice_type, int(item["id"]))
            original_total = float(item["total"])
            net_total = max(0.0, original_total - returned)
            paid = float(item["paid"])
            item["returned_total"] = returned
            item["net_total"] = net_total
            item["remaining"] = max(0.0, net_total - paid)
            item["credit_balance"] = max(0.0, paid - net_total)
            item["return_status"] = self._return_status(original_total, returned, invoice_type)
            item["payment_status"] = payment_status(
                net_total, min(paid, net_total), str(item["status"])
            )
        return rows

    def _returned_total(self, invoice_type: str, invoice_id: int) -> float:
        row = self.database.fetch_one(
            """
            SELECT COALESCE(SUM(total), 0) AS total
            FROM invoice_returns
            WHERE invoice_type = ? AND invoice_id = ?
            """,
            (invoice_type, invoice_id),
        )
        return float(row["total"] if row is not None else 0)

    @staticmethod
    def _return_status(original_total: float, returned: float, invoice_type: str) -> str:
        if returned <= EPSILON:
            return "مُسلَّمة" if invoice_type == "sales" else "مستلمة"
        if original_total - returned <= EPSILON:
            return "مرتجع كلي"
        return "مرتجع جزئي"

    def get_returnable_lines(self, invoice_type: str, invoice_id: int) -> list[dict]:
        if invoice_type == "sales":
            invoice_table = "sales_invoices"
            order_column = "sales_order_id"
            line_table = "sales_order_lines"
            line_fk = "sales_order_id"
        elif invoice_type == "purchase":
            invoice_table = "purchase_invoices"
            order_column = "purchase_order_id"
            line_table = "purchase_order_lines"
            line_fk = "purchase_order_id"
        else:
            raise ValueError("نوع الفاتورة غير صحيح")

        rows = self.database.fetch_all(
            f"""
            SELECT line.id AS order_line_id, line.product_id, product.code,
                   product.name, line.quantity, line.unit, line.unit_price,
                   line.line_total,
                   COALESCE((
                       SELECT SUM(irl.quantity)
                       FROM invoice_return_lines irl
                       JOIN invoice_returns ir ON ir.id = irl.return_id
                       WHERE ir.invoice_type = ? AND ir.invoice_id = ?
                         AND irl.order_line_id = line.id
                   ), 0) AS returned_quantity
            FROM {invoice_table} invoice
            JOIN {line_table} line ON line.{line_fk} = invoice.{order_column}
            JOIN products product ON product.id = line.product_id
            WHERE invoice.id = ? AND invoice.status = 'posted'
            ORDER BY line.id
            """,
            (invoice_type, invoice_id, invoice_id),
        )
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["remaining_quantity"] = max(
                0.0, float(item["quantity"]) - float(item["returned_quantity"])
            )
            result.append(item)
        return result

    def create_return(
        self,
        *,
        invoice_type: str,
        invoice_id: int,
        quantities: dict[int, float],
        reason: str,
    ) -> int:
        reason = reason.strip()
        if not reason:
            raise ValueError("سبب المرتجع مطلوب")
        available_lines = {
            int(line["order_line_id"]): line
            for line in self.get_returnable_lines(invoice_type, invoice_id)
        }
        normalized: list[dict] = []
        for line_id, raw_quantity in quantities.items():
            quantity = float(raw_quantity)
            if quantity <= EPSILON:
                continue
            line = available_lines.get(int(line_id))
            if line is None:
                raise ValueError("أحد بنود المرتجع غير موجود في الفاتورة")
            if quantity - float(line["remaining_quantity"]) > EPSILON:
                raise ValueError(
                    f"كمية مرتجع {line['name']} أكبر من الكمية المتبقية القابلة للإرجاع"
                )
            normalized.append({**line, "return_quantity": quantity})
        if not normalized:
            raise ValueError("أدخل كمية مرتجع لصنف واحد على الأقل")

        if invoice_type == "sales":
            invoice_table, order_column, party_column = (
                "sales_invoices",
                "sales_order_id",
                "customer_id",
            )
            prefix, reference_type = "SR", "sales_return"
        elif invoice_type == "purchase":
            invoice_table, order_column, party_column = (
                "purchase_invoices",
                "purchase_order_id",
                "supplier_id",
            )
            prefix, reference_type = "PR", "purchase_return"
        else:
            raise ValueError("نوع الفاتورة غير صحيح")

        with self.database.session(immediate=True) as connection:
            invoice = connection.execute(
                f"SELECT id, status, {order_column} AS order_id, {party_column} AS party_id "
                f"FROM {invoice_table} WHERE id = ?",
                (invoice_id,),
            ).fetchone()
            if invoice is None or str(invoice["status"]) != "posted":
                raise ValueError("يمكن عمل مرتجع لفاتورة معتمدة فقط")
            order_table = "sales_orders" if invoice_type == "sales" else "purchase_orders"
            order = connection.execute(
                f"SELECT warehouse_id FROM {order_table} WHERE id = ?",
                (int(invoice["order_id"]),),
            ).fetchone()
            if order is None:
                raise ValueError("أمر الفاتورة غير موجود")

            next_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM invoice_returns"
                ).fetchone()[0]
            )
            return_number = f"{prefix}{next_id:06d}"
            total = sum(
                float(line["return_quantity"]) * float(line["unit_price"]) for line in normalized
            )
            cursor = connection.execute(
                """
                INSERT INTO invoice_returns(
                    return_number, invoice_type, invoice_id, total, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (return_number, invoice_type, invoice_id, total, reason),
            )
            return_id = int(cursor.lastrowid)

            for line in normalized:
                quantity = float(line["return_quantity"])
                product_id = int(line["product_id"])
                unit_price = float(line["unit_price"])
                connection.execute(
                    """
                    INSERT INTO invoice_return_lines(
                        return_id, order_line_id, product_id, quantity,
                        unit, unit_price, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        return_id,
                        int(line["order_line_id"]),
                        product_id,
                        quantity,
                        str(line["unit"]),
                        unit_price,
                        quantity * unit_price,
                    ),
                )
                if invoice_type == "purchase":
                    self.costing_service.post_issue(
                        connection,
                        product_id=product_id,
                        warehouse_id=int(order["warehouse_id"]),
                        quantity=quantity,
                        reference_type=reference_type,
                        reference_id=return_id,
                        partner_id=int(invoice["party_id"]),
                        notes=f"{return_number} — {reason}",
                    )
                else:
                    cost_row = connection.execute(
                        """
                        SELECT COALESCE(SUM(quantity_out * unit_cost), 0) AS value,
                               COALESCE(SUM(quantity_out), 0) AS quantity
                        FROM inventory_moves
                        WHERE reference_type = 'sale' AND reference_id = ?
                          AND product_id = ?
                        """,
                        (int(invoice["order_id"]), product_id),
                    ).fetchone()
                    cost_quantity = float(cost_row["quantity"] or 0)
                    unit_cost = (
                        float(cost_row["value"] or 0) / cost_quantity
                        if cost_quantity > EPSILON
                        else 0.0
                    )
                    lot_number = (
                        f"RET-{return_number}-{product_id}-"
                        f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:4].upper()}"
                    )
                    lot_cursor = connection.execute(
                        "INSERT INTO lots(product_id, lot_number, unit_cost) VALUES (?, ?, ?)",
                        (product_id, lot_number, unit_cost),
                    )
                    connection.execute(
                        """
                        INSERT INTO inventory_moves(
                            product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                            unit_cost, reference_type, reference_id, partner_id, notes
                        ) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)
                        """,
                        (
                            product_id,
                            int(order["warehouse_id"]),
                            int(lot_cursor.lastrowid),
                            quantity,
                            unit_cost,
                            reference_type,
                            return_id,
                            int(invoice["party_id"]),
                            f"{return_number} — {reason}",
                        ),
                    )
            return return_id

    def list_returns(self, invoice_type: str, invoice_id: int) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT id, return_number, return_date, total, reason
            FROM invoice_returns
            WHERE invoice_type = ? AND invoice_id = ?
            ORDER BY id DESC
            """,
            (invoice_type, invoice_id),
        )
        return [dict(row) for row in rows]


__all__ = ["ReturnInvoiceRepository"]
