from app.database.connection import Database
from app.repositories.purchase_repository import PurchaseRepository
from app.services.payment_service import post_order_payment

EPSILON = 0.000001


class SupplierCostPurchaseRepository(PurchaseRepository):
    """Separates supplier payable from internal inventory capitalization.

    Supplier payable = purchased quantity x supplier unit price.
    Inventory value = supplier payable + internal processing cost, allocated over
    the net usable quantity after purchase loss.
    """

    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self._repair_existing_supplier_totals()

    def _repair_existing_supplier_totals(self) -> None:
        """Repair supplier totals and move legacy excess payments to advances."""
        with self.database.session(immediate=True) as connection:
            connection.execute(
                """
                UPDATE purchase_order_lines
                SET line_total = quantity * unit_price
                WHERE ABS(line_total - (quantity * unit_price)) > ?
                """,
                (EPSILON,),
            )
            connection.execute(
                """
                UPDATE purchase_invoices
                SET total = COALESCE((
                    SELECT SUM(pol.line_total)
                    FROM purchase_order_lines pol
                    WHERE pol.purchase_order_id = purchase_invoices.purchase_order_id
                ), 0)
                """
            )
            self._split_legacy_overpayments(connection)

    def _split_legacy_overpayments(self, connection) -> None:
        invoices = connection.execute(
            """
            SELECT id, purchase_order_id, supplier_id, invoice_number, total
            FROM purchase_invoices
            WHERE status = 'posted'
            ORDER BY id
            """
        ).fetchall()
        for invoice in invoices:
            transactions = connection.execute(
                """
                SELECT id, amount, payment_method, COALESCE(notes, '') AS notes
                FROM payment_transactions
                WHERE purchase_invoice_id = ?
                ORDER BY id DESC
                """,
                (invoice["id"],),
            ).fetchall()
            paid = sum(float(item["amount"]) for item in transactions)
            excess = paid - float(invoice["total"])
            if excess <= EPSILON:
                continue

            for transaction in transactions:
                if excess <= EPSILON:
                    break
                amount = float(transaction["amount"])
                moved = min(amount, excess)
                remaining = amount - moved
                if remaining > EPSILON:
                    connection.execute(
                        "UPDATE payment_transactions SET amount = ? WHERE id = ?",
                        (remaining, transaction["id"]),
                    )
                else:
                    connection.execute(
                        "DELETE FROM payment_transactions WHERE id = ?",
                        (transaction["id"],),
                    )

                post_order_payment(
                    connection,
                    transaction_type="supplier_payment",
                    partner_id=int(invoice["supplier_id"]),
                    amount=moved,
                    reference_type=None,
                    reference_id=None,
                    payment_method=str(transaction["payment_method"] or "نقدي"),
                    notes=(
                        f"دفعة مقدمة محولة تلقائيًا من زيادة سداد الفاتورة "
                        f"{invoice['invoice_number']}"
                    ),
                )
                excess -= moved

    def create_order_with_lines(
        self,
        *,
        supplier_id: int,
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
            lot_number = str(line.get("lot_number", "")).strip()
            quantity = float(line["quantity"])
            unit = str(line.get("unit", "")).strip() or "كجم"
            unit_price = float(line.get("unit_price", 0))
            manufacturing_unit_cost = float(line.get("manufacturing_unit_cost", 0) or 0)
            purchase_loss_quantity = float(line.get("purchase_loss_quantity", 0) or 0)

            if quantity <= 0:
                raise ValueError(f"كمية البند رقم {line_number} يجب أن تكون أكبر من صفر")
            if unit_price < 0:
                raise ValueError(f"سعر البند رقم {line_number} لا يمكن أن يكون سالبًا")
            if manufacturing_unit_cost < 0:
                raise ValueError(
                    f"تكلفة التجهيز الداخلي للبند رقم {line_number} لا يمكن أن تكون سالبة"
                )
            if purchase_loss_quantity < 0 or purchase_loss_quantity >= quantity:
                raise ValueError(f"فقد البند رقم {line_number} يجب أن يكون صفرًا أو أقل من الكمية")
            if not lot_number:
                raise ValueError(f"رقم الدفعة مطلوب في البند رقم {line_number}")

            net_quantity = quantity - purchase_loss_quantity
            supplier_total = quantity * unit_price
            internal_processing_total = quantity * manufacturing_unit_cost
            inventory_total = supplier_total + internal_processing_total

            normalized_lines.append(
                {
                    "product_id": product_id,
                    "lot_number": lot_number,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                    "manufacturing_unit_cost": manufacturing_unit_cost,
                    "purchase_loss_quantity": purchase_loss_quantity,
                    "net_quantity": net_quantity,
                    "inventory_unit_cost": inventory_total / net_quantity,
                    "line_total": supplier_total,
                }
            )

        supplier_order_total = sum(float(line["line_total"]) for line in normalized_lines)
        if paid_amount - supplier_order_total > EPSILON:
            raise ValueError("المدفوع لا يمكن أن يكون أكبر من إجمالي المستحق للمورد")

        with self.database.session(immediate=True) as connection:
            supplier = connection.execute(
                """
                SELECT id FROM partners
                WHERE id = ? AND partner_type = 'supplier' AND is_active = 1
                """,
                (supplier_id,),
            ).fetchone()
            if supplier is None:
                raise ValueError("المورد غير موجود أو غير نشط")

            warehouse_id = self.get_default_warehouse_id()
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
                        unit, unit_price, manufacturing_unit_cost,
                        purchase_loss_quantity, net_quantity,
                        inventory_unit_cost, line_total
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        line["product_id"],
                        line["lot_number"],
                        line["quantity"],
                        line["unit"],
                        line["unit_price"],
                        line["manufacturing_unit_cost"],
                        line["purchase_loss_quantity"],
                        line["net_quantity"],
                        line["inventory_unit_cost"],
                        line["line_total"],
                    ),
                )

            if paid_amount > 0:
                post_order_payment(
                    connection,
                    transaction_type="supplier_payment",
                    partner_id=supplier_id,
                    amount=paid_amount,
                    reference_type="purchase",
                    reference_id=order_id,
                    notes=f"دفعة عند إنشاء أمر الشراء {order_number}",
                )
            return order_id


__all__ = ["SupplierCostPurchaseRepository"]
