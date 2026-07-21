from __future__ import annotations

from collections import defaultdict

from app.repositories.sales_repository import SalesRepository
from app.services.weight_invoice_calculator import (
    calculate_net_weight,
    calculate_weight_invoice,
)

EPSILON = 0.0000001


class WeightInvoiceRepository(SalesRepository):
    """Independent draft, approval and printing workflow for weight sales."""

    def preview_document_numbers(self) -> dict[str, str]:
        row = self.database.fetch_one(
            """
            SELECT
                (SELECT COALESCE(MAX(id), 0) + 1 FROM sales_orders) AS order_id,
                (SELECT COALESCE(MAX(id), 0) + 1 FROM sales_invoices) AS invoice_id,
                (SELECT COALESCE(MAX(id), 0) + 1 FROM sales_weight_cards) AS card_id
            """
        )
        return {
            "order_number": f"SO{int(row['order_id']):05d}",
            "invoice_number": f"SI{int(row['invoice_id']):05d}",
            "card_number": f"WC{int(row['card_id']):06d}",
        }

    def create_weight_sale(
        self,
        *,
        customer_id: int,
        lines: list[dict],
        net_weight_kg: float | None = None,
        price_per_kg: float = 0,
        card_number: str = "",
        vehicle_number: str = "",
        gross_weight_kg: float | None = None,
        tare_weight_kg: float | None = None,
        notes: str = "",
        weight_mode: str = "total_card",
        pricing_mode: str = "uniform",
        use_vehicle_scale: bool = False,
        discount_amount: float = 0,
        transport_amount: float = 0,
        tax_amount: float = 0,
        sale_date: str | None = None,
    ) -> dict:
        """Backward-compatible entry point that now creates a true draft."""
        return self.create_weight_sale_draft(
            customer_id=customer_id,
            lines=lines,
            net_weight_kg=net_weight_kg,
            uniform_price_per_kg=price_per_kg,
            card_number=card_number,
            vehicle_number=vehicle_number,
            gross_weight_kg=gross_weight_kg,
            tare_weight_kg=tare_weight_kg,
            notes=notes,
            weight_mode=weight_mode,
            pricing_mode=pricing_mode,
            use_vehicle_scale=use_vehicle_scale,
            discount_amount=discount_amount,
            transport_amount=transport_amount,
            tax_amount=tax_amount,
            sale_date=sale_date,
        )

    def create_weight_sale_draft(
        self,
        *,
        customer_id: int,
        lines: list[dict],
        weight_mode: str,
        pricing_mode: str,
        net_weight_kg: float | None = None,
        uniform_price_per_kg: float | None = None,
        card_number: str = "",
        vehicle_number: str = "",
        gross_weight_kg: float | None = None,
        tare_weight_kg: float | None = None,
        use_vehicle_scale: bool = False,
        discount_amount: float = 0,
        transport_amount: float = 0,
        tax_amount: float = 0,
        sale_date: str | None = None,
        notes: str = "",
    ) -> dict:
        discount, transport, tax = self._normalize_adjustments(
            discount_amount,
            transport_amount,
            tax_amount,
        )
        with self.database.session(immediate=True) as connection:
            customer = connection.execute(
                """
                SELECT id FROM partners
                WHERE id = ? AND partner_type = 'customer' AND is_active = 1
                """,
                (int(customer_id),),
            ).fetchone()
            if customer is None:
                raise ValueError("العميل غير موجود أو غير نشط")
            warehouse = connection.execute(
                "SELECT id FROM warehouses WHERE code = 'MAIN' AND is_active = 1"
            ).fetchone()
            if warehouse is None:
                raise ValueError("مخزن المصنع غير موجود")

            product_ids = [int(item["product_id"]) for item in lines]
            if not product_ids:
                raise ValueError("أضف بندًا واحدًا على الأقل")
            placeholders = ",".join("?" for _ in product_ids)
            products = {
                int(row["id"]): row
                for row in connection.execute(
                    f"""
                    SELECT id, code, name, unit, product_type,
                           COALESCE(standard_weight_kg, 0) AS standard_weight_kg
                    FROM products
                    WHERE id IN ({placeholders}) AND is_active = 1
                    """,
                    tuple(product_ids),
                ).fetchall()
            }
            prepared_lines: list[dict] = []
            seen: set[int] = set()
            for source in lines:
                product_id = int(source["product_id"])
                if product_id in seen:
                    raise ValueError("لا تكرر نفس المقاس داخل الفاتورة؛ عدّل كميته في البند الحالي")
                seen.add(product_id)
                product = products.get(product_id)
                if product is None or str(product["product_type"]) != "finished_good":
                    raise ValueError("يوجد صنف غير صالح للبيع بالوزن")
                prepared_lines.append(
                    {
                        **source,
                        "product_id": product_id,
                        "code": str(product["code"]),
                        "name": str(product["name"]),
                        "unit": str(source.get("unit") or product["unit"] or "ماسورة"),
                        "standard_weight_kg": float(product["standard_weight_kg"] or 0),
                    }
                )

            if weight_mode == "total_card":
                actual_net = calculate_net_weight(
                    net_weight_kg=net_weight_kg,
                    use_vehicle_scale=use_vehicle_scale,
                    gross_weight_kg=gross_weight_kg,
                    tare_weight_kg=tare_weight_kg,
                )
            else:
                actual_net = None

            calculation = calculate_weight_invoice(
                lines=prepared_lines,
                weight_mode=weight_mode,
                pricing_mode=pricing_mode,
                total_actual_weight_kg=actual_net,
                uniform_price_per_kg=uniform_price_per_kg,
            )
            if weight_mode == "per_line" and use_vehicle_scale:
                scale_net = calculate_net_weight(
                    use_vehicle_scale=True,
                    gross_weight_kg=gross_weight_kg,
                    tare_weight_kg=tare_weight_kg,
                )
                if abs(scale_net - float(calculation["total_actual_weight_kg"])) > 0.001:
                    raise ValueError(
                        "مجموع أوزان البنود لا يساوي صافي وزن ميزان السيارة"
                    )
            actual_net = float(calculation["total_actual_weight_kg"])
            subtotal = float(calculation["subtotal"])
            net_total = subtotal - discount + transport + tax
            if net_total < -EPSILON:
                raise ValueError("صافي الفاتورة لا يمكن أن يكون سالبًا")

            next_order_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM sales_orders"
                ).fetchone()[0]
            )
            order_number = f"SO{next_order_id:05d}"
            order_cursor = connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, order_date,
                    status, notes, billing_method, weight_card_total,
                    weight_mode, weight_pricing_mode
                ) VALUES (?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP), 'draft', ?,
                          'weight', ?, ?, ?)
                """,
                (
                    order_number,
                    int(customer_id),
                    int(warehouse["id"]),
                    sale_date,
                    notes.strip(),
                    subtotal,
                    weight_mode,
                    pricing_mode,
                ),
            )
            order_id = int(order_cursor.lastrowid)

            order_line_ids: list[int] = []
            for line in calculation["lines"]:
                quantity = float(line["quantity"])
                line_total = float(line["line_total"])
                effective_piece_price = line_total / quantity if quantity > EPSILON else 0
                cursor = connection.execute(
                    """
                    INSERT INTO sales_order_lines(
                        sales_order_id, product_id, quantity, unit,
                        unit_price, line_total, billing_weight_kg, price_per_kg
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        int(line["product_id"]),
                        quantity,
                        str(line["unit"]),
                        effective_piece_price,
                        line_total,
                        float(line["allocated_weight_kg"]),
                        float(line["price_per_kg"]),
                    ),
                )
                order_line_ids.append(int(cursor.lastrowid))

            next_card_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM sales_weight_cards"
                ).fetchone()[0]
            )
            generated_card_number = card_number.strip() or f"WC{next_card_id:06d}"
            card_cursor = connection.execute(
                """
                INSERT INTO sales_weight_cards(
                    sales_order_id, card_number, card_date, vehicle_number,
                    gross_weight_kg, tare_weight_kg, net_weight_kg,
                    price_per_kg, total_amount, status, notes,
                    weight_mode, pricing_mode, use_vehicle_scale,
                    discount_amount, transport_amount, tax_amount, net_amount
                ) VALUES (?, ?, COALESCE(?, CURRENT_TIMESTAMP), ?, ?, ?, ?, ?, ?,
                          'draft', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_id,
                    generated_card_number,
                    sale_date,
                    vehicle_number.strip(),
                    None if gross_weight_kg is None else float(gross_weight_kg),
                    None if tare_weight_kg is None else float(tare_weight_kg),
                    actual_net,
                    float(calculation["uniform_price_per_kg"]),
                    subtotal,
                    notes.strip(),
                    weight_mode,
                    pricing_mode,
                    1 if use_vehicle_scale else 0,
                    discount,
                    transport,
                    tax,
                    max(0.0, net_total),
                ),
            )
            card_id = int(card_cursor.lastrowid)
            for order_line_id, line in zip(order_line_ids, calculation["lines"], strict=True):
                connection.execute(
                    """
                    INSERT INTO sales_weight_card_lines(
                        weight_card_id, sales_order_line_id, product_id,
                        quantity_pieces, standard_weight_kg,
                        theoretical_weight_kg, allocated_weight_kg, line_total,
                        actual_weight_kg, price_per_kg, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card_id,
                        order_line_id,
                        int(line["product_id"]),
                        float(line["quantity"]),
                        float(line["standard_weight_kg"]),
                        float(line["theoretical_weight_kg"]),
                        float(line["allocated_weight_kg"]),
                        float(line["line_total"]),
                        float(line["actual_weight_kg"]),
                        float(line["price_per_kg"]),
                        str(line.get("notes") or ""),
                    ),
                )

            return {
                "order_id": order_id,
                "order_number": order_number,
                "card_id": card_id,
                "card_number": generated_card_number,
                "invoice_number": "",
                "status": "draft",
                "subtotal": subtotal,
                "net_total": max(0.0, net_total),
            }

    def approve_weight_sale(self, order_id: int) -> dict:
        """Post inventory count and actual weight, then create the customer debt."""
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                """
                SELECT so.*, p.name AS customer_name
                FROM sales_orders so
                JOIN partners p ON p.id = so.customer_id
                WHERE so.id = ? AND so.billing_method = 'weight'
                """,
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("فاتورة البيع بالوزن غير موجودة")
            if str(order["status"]) == "delivered":
                invoice = connection.execute(
                    "SELECT id, invoice_number FROM sales_invoices WHERE sales_order_id = ?",
                    (int(order_id),),
                ).fetchone()
                return {
                    "order_id": int(order_id),
                    "invoice_id": int(invoice["id"]),
                    "invoice_number": str(invoice["invoice_number"]),
                }
            if str(order["status"]) != "draft":
                raise ValueError("لا يمكن اعتماد مستند ملغى أو غير مسودة")

            card = connection.execute(
                """
                SELECT * FROM sales_weight_cards
                WHERE sales_order_id = ? AND status = 'draft'
                ORDER BY id LIMIT 1
                """,
                (int(order_id),),
            ).fetchone()
            if card is None or float(card["net_weight_kg"] or 0) <= EPSILON:
                raise ValueError("لا يمكن الاعتماد قبل إدخال وزن فعلي صحيح")
            lines = connection.execute(
                """
                SELECT wcl.*, sol.unit
                FROM sales_weight_card_lines wcl
                JOIN sales_order_lines sol ON sol.id = wcl.sales_order_line_id
                WHERE wcl.weight_card_id = ? ORDER BY wcl.id
                """,
                (int(card["id"]),),
            ).fetchall()
            if not lines:
                raise ValueError("فاتورة الوزن لا تحتوي على بنود")

            required_count: dict[int, float] = defaultdict(float)
            for line in lines:
                quantity = float(line["quantity_pieces"] or 0)
                weight = float(line["allocated_weight_kg"] or 0)
                if quantity <= EPSILON or weight <= EPSILON:
                    raise ValueError("كل بند يجب أن يحتوي على عدد ووزن فعلي")
                required_count[int(line["product_id"])] += quantity

            for product_id, quantity in required_count.items():
                available_count = float(
                    connection.execute(
                        """
                        SELECT COALESCE(SUM(quantity_in - quantity_out), 0)
                        FROM inventory_moves
                        WHERE product_id = ? AND warehouse_id = ?
                        """,
                        (product_id, int(order["warehouse_id"])),
                    ).fetchone()[0]
                )
                if quantity - available_count > EPSILON:
                    raise ValueError(
                        f"عدد المواسير المطلوب أكبر من المتاح بالمخزون ({available_count:g})"
                    )

            for line in lines:
                self.costing_service.post_issue(
                    connection,
                    product_id=int(line["product_id"]),
                    warehouse_id=int(order["warehouse_id"]),
                    quantity=float(line["quantity_pieces"]),
                    reference_type="sale",
                    reference_id=int(order_id),
                    partner_id=int(order["customer_id"]),
                    notes=f"{order['order_number']} / {card['card_number']}",
                )
                self._allocate_weight_line(connection, order, line)

            connection.execute(
                "UPDATE sales_orders SET status = 'delivered' WHERE id = ?",
                (int(order_id),),
            )
            invoice = connection.execute(
                "SELECT id, invoice_number FROM sales_invoices WHERE sales_order_id = ?",
                (int(order_id),),
            ).fetchone()
            if invoice is None:
                next_invoice_id = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(id), 0) + 1 FROM sales_invoices"
                    ).fetchone()[0]
                )
                invoice_number = f"SI{next_invoice_id:05d}"
                cursor = connection.execute(
                    """
                    INSERT INTO sales_invoices(
                        invoice_number, sales_order_id, customer_id, invoice_date,
                        status, total, notes, posted_at, invoice_type,
                        discount_amount, transport_amount, tax_amount, net_total
                    ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'posted', ?, ?,
                              CURRENT_TIMESTAMP, 'weight', ?, ?, ?, ?)
                    """,
                    (
                        invoice_number,
                        int(order_id),
                        int(order["customer_id"]),
                        float(card["net_amount"]),
                        str(card["notes"] or ""),
                        float(card["discount_amount"]),
                        float(card["transport_amount"]),
                        float(card["tax_amount"]),
                        float(card["net_amount"]),
                    ),
                )
                invoice_id = int(cursor.lastrowid)
            else:
                invoice_id = int(invoice["id"])
                invoice_number = str(invoice["invoice_number"])
                connection.execute(
                    """
                    UPDATE sales_invoices
                    SET status = 'posted', posted_at = CURRENT_TIMESTAMP,
                        invoice_type = 'weight', total = ?, net_total = ?,
                        discount_amount = ?, transport_amount = ?, tax_amount = ?
                    WHERE id = ?
                    """,
                    (
                        float(card["net_amount"]),
                        float(card["net_amount"]),
                        float(card["discount_amount"]),
                        float(card["transport_amount"]),
                        float(card["tax_amount"]),
                        invoice_id,
                    ),
                )

            connection.execute(
                """
                UPDATE sales_weight_cards
                SET status = 'posted', sales_invoice_id = ?
                WHERE id = ?
                """,
                (invoice_id, int(card["id"])),
            )
            connection.execute(
                """
                UPDATE payment_transactions
                SET sales_invoice_id = ?
                WHERE transaction_type = 'customer_receipt'
                  AND reference_type = 'sale' AND reference_id = ?
                  AND sales_invoice_id IS NULL
                """,
                (invoice_id, int(order_id)),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO payment_allocations(
                    transaction_id, sales_invoice_id, amount
                )
                SELECT id, ?, amount FROM payment_transactions
                WHERE transaction_type = 'customer_receipt'
                  AND reference_type = 'sale' AND reference_id = ?
                  AND amount > 0
                """,
                (invoice_id, int(order_id)),
            )
            return {
                "order_id": int(order_id),
                "order_number": str(order["order_number"]),
                "card_id": int(card["id"]),
                "card_number": str(card["card_number"]),
                "invoice_id": invoice_id,
                "invoice_number": invoice_number,
                "net_total": float(card["net_amount"]),
            }

    def deliver_weight_sale(self, order_id: int) -> None:
        self.approve_weight_sale(int(order_id))

    def approve_and_get_print_data(self, order_id: int) -> dict:
        result = self.approve_weight_sale(int(order_id))
        return self.get_weight_invoice_print_data(int(result["invoice_id"]))

    def _allocate_weight_line(self, connection, order, line) -> None:
        remaining_quantity = float(line["quantity_pieces"])
        remaining_weight = float(line["allocated_weight_kg"])
        average_weight = remaining_weight / remaining_quantity
        layers = connection.execute(
            """
            SELECT *, quantity_in - quantity_out AS available_quantity,
                      weight_in_kg - weight_out_kg AS available_weight
            FROM finished_good_weight_layers
            WHERE product_id = ? AND warehouse_id = ?
              AND quantity_in - quantity_out > 0.0000001
              AND weight_in_kg - weight_out_kg > 0.0000001
            ORDER BY id
            """,
            (int(line["product_id"]), int(order["warehouse_id"])),
        ).fetchall()
        for layer in layers:
            if remaining_quantity <= EPSILON:
                break
            take_quantity = min(
                remaining_quantity,
                float(layer["available_quantity"]),
                float(layer["available_weight"]) / average_weight,
            )
            if take_quantity <= EPSILON:
                continue
            take_weight = (
                remaining_weight
                if remaining_quantity - take_quantity <= EPSILON
                else take_quantity * average_weight
            )
            cost_amount = take_weight * float(layer["unit_cost_per_kg"] or 0)
            connection.execute(
                """
                INSERT INTO sales_weight_inventory_allocations(
                    weight_card_line_id, weight_layer_id,
                    quantity_pieces, weight_kg, cost_amount
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(line["id"]),
                    int(layer["id"]),
                    take_quantity,
                    take_weight,
                    cost_amount,
                ),
            )
            connection.execute(
                """
                UPDATE finished_good_weight_layers
                SET quantity_out = quantity_out + ?,
                    weight_out_kg = weight_out_kg + ?
                WHERE id = ?
                """,
                (take_quantity, take_weight, int(layer["id"])),
            )
            remaining_quantity -= take_quantity
            remaining_weight -= take_weight
        if remaining_quantity > EPSILON or remaining_weight > EPSILON:
            # Stock created before weight-layer tracking is still valid by piece count.
            # Preserve the card's actual commercial weight without blocking approval.
            connection.execute(
                """
                INSERT INTO sales_weight_inventory_allocations(
                    weight_card_line_id, weight_layer_id,
                    quantity_pieces, weight_kg, cost_amount
                ) VALUES (?, NULL, ?, ?, 0)
                """,
                (
                    int(line["id"]),
                    max(remaining_quantity, EPSILON),
                    max(remaining_weight, EPSILON),
                ),
            )

    def get_weight_sale(self, order_id: int) -> dict:
        row = self.database.fetch_one(
            """
            SELECT so.id AS order_id, so.order_number, so.order_date, so.status,
                   so.customer_id, so.warehouse_id, p.name AS customer_name,
                   w.name AS warehouse_name, wc.*,
                   COALESCE(si.invoice_number, '') AS invoice_number,
                   COALESCE(si.id, 0) AS invoice_id,
                   COALESCE((
                       SELECT SUM(pa.amount) FROM payment_allocations pa
                       WHERE pa.sales_invoice_id = si.id
                   ), 0) AS paid
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            JOIN sales_weight_cards wc ON wc.sales_order_id = so.id
            LEFT JOIN sales_invoices si ON si.id = wc.sales_invoice_id
            WHERE so.id = ? AND so.billing_method = 'weight'
            ORDER BY wc.id LIMIT 1
            """,
            (int(order_id),),
        )
        if row is None:
            raise ValueError("فاتورة البيع بالوزن غير موجودة")
        result = dict(row)
        result["lines"] = [
            dict(line)
            for line in self.database.fetch_all(
                """
                SELECT wcl.*, p.code, p.name, sol.unit
                FROM sales_weight_card_lines wcl
                JOIN products p ON p.id = wcl.product_id
                JOIN sales_order_lines sol ON sol.id = wcl.sales_order_line_id
                WHERE wcl.weight_card_id = ? ORDER BY wcl.id
                """,
                (int(result["id"]),),
            )
        ]
        result["remaining"] = max(
            0.0,
            float(result["net_amount"] or 0) - float(result["paid"] or 0),
        )
        return result

    def list_weight_sales(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT so.id AS order_id, so.order_number, so.order_date, so.status,
                   p.name AS customer_name, w.name AS warehouse_name,
                   wc.id AS card_id, wc.card_number, wc.vehicle_number,
                   wc.net_weight_kg, wc.price_per_kg, wc.total_amount,
                   wc.net_amount, wc.status AS card_status, wc.notes,
                   wc.weight_mode, wc.pricing_mode,
                   COALESCE(si.id, 0) AS invoice_id,
                   COALESCE(si.invoice_number, '') AS invoice_number,
                   COALESCE((SELECT SUM(pa.amount) FROM payment_allocations pa
                             WHERE pa.sales_invoice_id = si.id), 0) AS paid,
                   COALESCE(SUM(wcl.quantity_pieces), 0) AS total_pieces,
                   COUNT(DISTINCT wcl.product_id) AS product_count
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            JOIN sales_weight_cards wc ON wc.sales_order_id = so.id
            LEFT JOIN sales_invoices si ON si.id = wc.sales_invoice_id
            LEFT JOIN sales_weight_card_lines wcl ON wcl.weight_card_id = wc.id
            WHERE so.billing_method = 'weight' AND wc.status <> 'cancelled'
            GROUP BY so.id, wc.id, si.id
            ORDER BY so.id DESC, wc.id DESC
            """
        )
        result = []
        for row in rows:
            item = dict(row)
            item["remaining"] = max(
                0.0,
                float(item["net_amount"] or 0) - float(item["paid"] or 0),
            )
            result.append(item)
        return result

    def delete_draft_weight_sale(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT status FROM sales_orders WHERE id = ? AND billing_method = 'weight'",
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("بيع الوزن غير موجود")
            if str(order["status"]) != "draft":
                raise ValueError("لا يمكن حذف فاتورة وزن معتمدة")
            connection.execute(
                """
                DELETE FROM sales_weight_card_lines
                WHERE weight_card_id IN (
                    SELECT id FROM sales_weight_cards WHERE sales_order_id = ?
                )
                """,
                (int(order_id),),
            )
            connection.execute(
                "DELETE FROM sales_weight_cards WHERE sales_order_id = ?",
                (int(order_id),),
            )
            connection.execute(
                "DELETE FROM sales_order_lines WHERE sales_order_id = ?",
                (int(order_id),),
            )
            connection.execute(
                "DELETE FROM sales_orders WHERE id = ?",
                (int(order_id),),
            )

    def get_weight_invoice_print_data(self, invoice_id: int) -> dict:
        row = self.database.fetch_one(
            """
            SELECT si.id, si.invoice_number, si.invoice_date, si.status,
                   si.total, si.net_total, si.discount_amount,
                   si.transport_amount, si.tax_amount, so.order_number,
                   p.name AS customer_name, COALESCE(p.code, '') AS customer_code,
                   COALESCE(p.phone, '') AS customer_phone,
                   COALESCE(p.address, '') AS customer_address,
                   wc.id AS card_id, wc.card_number, wc.vehicle_number,
                   wc.net_weight_kg, wc.total_amount AS subtotal,
                   wc.weight_mode, wc.pricing_mode, wc.notes,
                   COALESCE((SELECT SUM(pa.amount) FROM payment_allocations pa
                             WHERE pa.sales_invoice_id = si.id), 0) AS paid
            FROM sales_invoices si
            JOIN sales_orders so ON so.id = si.sales_order_id
            JOIN partners p ON p.id = si.customer_id
            JOIN sales_weight_cards wc ON wc.sales_invoice_id = si.id
            WHERE si.id = ? AND si.invoice_type = 'weight'
            """,
            (int(invoice_id),),
        )
        if row is None:
            raise ValueError("فاتورة الوزن غير موجودة")
        if str(row["status"]) != "posted":
            raise ValueError("يمكن طباعة فاتورة الوزن المعتمدة فقط")
        result = dict(row)
        result["lines"] = [
            dict(line)
            for line in self.database.fetch_all(
                """
                SELECT p.code, p.name, sol.unit, wcl.quantity_pieces AS quantity,
                       wcl.actual_weight_kg, wcl.allocated_weight_kg,
                       wcl.price_per_kg, wcl.line_total, wcl.notes,
                       wcl.standard_weight_kg, wcl.theoretical_weight_kg
                FROM sales_weight_card_lines wcl
                JOIN products p ON p.id = wcl.product_id
                JOIN sales_order_lines sol ON sol.id = wcl.sales_order_line_id
                WHERE wcl.weight_card_id = ? ORDER BY wcl.id
                """,
                (int(result["card_id"]),),
            )
        ]
        result["total_pieces"] = sum(
            float(line["quantity"]) for line in result["lines"]
        )
        result["remaining"] = max(
            0.0,
            float(result["net_total"] or result["total"] or 0)
            - float(result["paid"] or 0),
        )
        return result

    @staticmethod
    def _normalize_adjustments(discount: float, transport: float, tax: float) -> tuple[float, float, float]:
        values = (float(discount or 0), float(transport or 0), float(tax or 0))
        if any(value < 0 for value in values):
            raise ValueError("الخصم والنقل والضريبة لا يمكن أن تكون سالبة")
        return values


__all__ = ["WeightInvoiceRepository"]
