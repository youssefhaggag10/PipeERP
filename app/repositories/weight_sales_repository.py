from __future__ import annotations

from app.repositories.sales_repository import SalesRepository

EPSILON = 0.0000001


class WeightSalesRepository(SalesRepository):
    """Sales repository supporting mixed-size truck weight cards.

    Inventory is still delivered in pipe pieces. Commercial value is calculated
    from the scale's actual net kilograms multiplied by the card's kilogram price.
    The centralized database migrations own the weight-card schema.
    """

    def create_weight_card(
        self,
        sales_order_id: int,
        *,
        lines: list[dict],
        net_weight_kg: float,
        price_per_kg: float,
        card_number: str = "",
        vehicle_number: str = "",
        gross_weight_kg: float | None = None,
        tare_weight_kg: float | None = None,
        notes: str = "",
    ) -> int:
        net_weight_kg = float(net_weight_kg)
        price_per_kg = float(price_per_kg)
        if net_weight_kg <= EPSILON:
            raise ValueError("أدخل الوزن الصافي الفعلي للكارتة")
        if price_per_kg < 0:
            raise ValueError("سعر الكيلو لا يمكن أن يكون سالبًا")
        normalized = [
            {
                "sales_order_line_id": int(item["sales_order_line_id"]),
                "quantity_pieces": float(item.get("quantity_pieces", 0) or 0),
            }
            for item in lines
            if float(item.get("quantity_pieces", 0) or 0) > EPSILON
        ]
        if not normalized:
            raise ValueError("أضف عدد المواسير الموجودة على الكارتة")

        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT id, status FROM sales_orders WHERE id = ?",
                (int(sales_order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("أمر البيع غير موجود")
            if str(order["status"]) != "draft":
                raise ValueError("يمكن إضافة كارتة وزن لأمر بيع مسودة فقط")

            order_lines = {
                int(row["id"]): row
                for row in connection.execute(
                    """
                    SELECT sol.id, sol.product_id, sol.quantity, p.code, p.name,
                           COALESCE(p.standard_weight_kg, 0) AS standard_weight_kg
                    FROM sales_order_lines sol
                    JOIN products p ON p.id = sol.product_id
                    WHERE sol.sales_order_id = ?
                    """,
                    (int(sales_order_id),),
                ).fetchall()
            }
            selected_ids = {item["sales_order_line_id"] for item in normalized}
            if not selected_ids.issubset(order_lines):
                raise ValueError("يوجد بند لا ينتمي إلى أمر البيع المحدد")

            allocated_before = {
                int(row["sales_order_line_id"]): float(row["quantity_pieces"] or 0)
                for row in connection.execute(
                    """
                    SELECT wcl.sales_order_line_id, SUM(wcl.quantity_pieces) AS quantity_pieces
                    FROM sales_weight_card_lines wcl
                    JOIN sales_weight_cards wc ON wc.id = wcl.weight_card_id
                    WHERE wc.sales_order_id = ? AND wc.status <> 'cancelled'
                    GROUP BY wcl.sales_order_line_id
                    """,
                    (int(sales_order_id),),
                ).fetchall()
            }

            theoretical_total = 0.0
            quantity_total = 0.0
            prepared: list[dict] = []
            for item in normalized:
                line = order_lines[item["sales_order_line_id"]]
                quantity = item["quantity_pieces"]
                already = allocated_before.get(int(line["id"]), 0.0)
                if already + quantity - float(line["quantity"]) > EPSILON:
                    available = max(0.0, float(line["quantity"]) - already)
                    raise ValueError(
                        f"عدد {line['name']} على الكارتة أكبر من المتبقي. المتاح {available:g} ماسورة"
                    )
                standard = float(line["standard_weight_kg"] or 0)
                theoretical = quantity * standard
                theoretical_total += theoretical
                quantity_total += quantity
                prepared.append(
                    {
                        "line": line,
                        "quantity": quantity,
                        "standard": standard,
                        "theoretical": theoretical,
                    }
                )

            if theoretical_total <= EPSILON and quantity_total <= EPSILON:
                raise ValueError("تعذر توزيع وزن الكارتة على البنود")

            if not card_number.strip():
                next_id = int(
                    connection.execute(
                        "SELECT COALESCE(MAX(id), 0) + 1 AS n FROM sales_weight_cards"
                    ).fetchone()["n"]
                )
                card_number = f"WC{next_id:05d}"
            total_amount = net_weight_kg * price_per_kg
            cursor = connection.execute(
                """
                INSERT INTO sales_weight_cards(
                    sales_order_id, card_number, vehicle_number,
                    gross_weight_kg, tare_weight_kg, net_weight_kg,
                    price_per_kg, total_amount, status, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'posted', ?)
                """,
                (
                    int(sales_order_id),
                    card_number.strip(),
                    vehicle_number.strip(),
                    None if gross_weight_kg is None else float(gross_weight_kg),
                    None if tare_weight_kg is None else float(tare_weight_kg),
                    net_weight_kg,
                    price_per_kg,
                    total_amount,
                    notes.strip(),
                ),
            )
            card_id = int(cursor.lastrowid)

            remaining_weight = net_weight_kg
            for index, item in enumerate(prepared):
                if index == len(prepared) - 1:
                    allocated_weight = remaining_weight
                elif theoretical_total > EPSILON:
                    allocated_weight = net_weight_kg * item["theoretical"] / theoretical_total
                else:
                    allocated_weight = net_weight_kg * item["quantity"] / quantity_total
                allocated_weight = max(0.0, allocated_weight)
                remaining_weight -= allocated_weight
                line_total = allocated_weight * price_per_kg
                connection.execute(
                    """
                    INSERT INTO sales_weight_card_lines(
                        weight_card_id, sales_order_line_id, product_id,
                        quantity_pieces, standard_weight_kg, theoretical_weight_kg,
                        allocated_weight_kg, line_total
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        card_id,
                        int(item["line"]["id"]),
                        int(item["line"]["product_id"]),
                        item["quantity"],
                        item["standard"],
                        item["theoretical"],
                        allocated_weight,
                        line_total,
                    ),
                )

            self._reprice_order(connection, int(sales_order_id))
            return card_id

    def cancel_weight_card(self, card_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            card = connection.execute(
                "SELECT id, sales_order_id, status FROM sales_weight_cards WHERE id = ?",
                (int(card_id),),
            ).fetchone()
            if card is None:
                raise ValueError("كارتة الوزن غير موجودة")
            order = connection.execute(
                "SELECT status FROM sales_orders WHERE id = ?",
                (int(card["sales_order_id"]),),
            ).fetchone()
            if order is None or str(order["status"]) != "draft":
                raise ValueError("لا يمكن إلغاء الكارتة بعد تسليم أمر البيع")
            connection.execute(
                "UPDATE sales_weight_cards SET status = 'cancelled' WHERE id = ?",
                (int(card_id),),
            )
            self._reprice_order(connection, int(card["sales_order_id"]))

    def list_weight_cards(self, sales_order_id: int) -> list[dict]:
        return [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT wc.*,
                       COALESCE(SUM(wcl.quantity_pieces), 0) AS total_pieces,
                       COUNT(wcl.id) AS line_count
                FROM sales_weight_cards wc
                LEFT JOIN sales_weight_card_lines wcl ON wcl.weight_card_id = wc.id
                WHERE wc.sales_order_id = ?
                GROUP BY wc.id ORDER BY wc.id
                """,
                (int(sales_order_id),),
            )
        ]

    def get_weight_card(self, card_id: int) -> dict:
        card = self.database.fetch_one(
            "SELECT * FROM sales_weight_cards WHERE id = ?",
            (int(card_id),),
        )
        if card is None:
            raise ValueError("كارتة الوزن غير موجودة")
        result = dict(card)
        result["lines"] = [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT wcl.*, p.code, p.name
                FROM sales_weight_card_lines wcl
                JOIN products p ON p.id = wcl.product_id
                WHERE wcl.weight_card_id = ? ORDER BY wcl.id
                """,
                (int(card_id),),
            )
        ]
        return result

    def get_order_weight_lines(self, sales_order_id: int) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT sol.id AS sales_order_line_id, sol.product_id, p.code, p.name,
                   sol.quantity AS ordered_quantity,
                   COALESCE(p.standard_weight_kg, 0) AS standard_weight_kg,
                   COALESCE((
                       SELECT SUM(wcl.quantity_pieces)
                       FROM sales_weight_card_lines wcl
                       JOIN sales_weight_cards wc ON wc.id = wcl.weight_card_id
                       WHERE wcl.sales_order_line_id = sol.id AND wc.status <> 'cancelled'
                   ), 0) AS allocated_quantity,
                   COALESCE((
                       SELECT SUM(wcl.allocated_weight_kg)
                       FROM sales_weight_card_lines wcl
                       JOIN sales_weight_cards wc ON wc.id = wcl.weight_card_id
                       WHERE wcl.sales_order_line_id = sol.id AND wc.status <> 'cancelled'
                   ), 0) AS allocated_weight_kg
            FROM sales_order_lines sol
            JOIN products p ON p.id = sol.product_id
            WHERE sol.sales_order_id = ? ORDER BY sol.id
            """,
            (int(sales_order_id),),
        )
        result = []
        for row in rows:
            item = dict(row)
            item["remaining_quantity"] = max(
                0.0,
                float(item["ordered_quantity"]) - float(item["allocated_quantity"]),
            )
            result.append(item)
        return result

    def deliver_order(self, order_id: int) -> None:
        order = self.database.fetch_one(
            "SELECT billing_method FROM sales_orders WHERE id = ?",
            (int(order_id),),
        )
        if order is None:
            raise ValueError("أمر البيع غير موجود")
        if str(order["billing_method"]) == "weight":
            missing = [
                row
                for row in self.get_order_weight_lines(int(order_id))
                if float(row["remaining_quantity"]) > EPSILON
            ]
            if missing:
                names = "، ".join(
                    f"{row['name']} ({float(row['remaining_quantity']):g})" for row in missing
                )
                raise ValueError(f"أكمل كروت الوزن لكل مواسير الأمر أولًا: {names}")

        super().deliver_order(int(order_id))
        if str(order["billing_method"]) == "weight":
            self._allocate_delivered_weight(int(order_id))

    def _allocate_delivered_weight(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT warehouse_id FROM sales_orders WHERE id = ?",
                (int(order_id),),
            ).fetchone()
            lines = connection.execute(
                """
                SELECT wcl.*
                FROM sales_weight_card_lines wcl
                JOIN sales_weight_cards wc ON wc.id = wcl.weight_card_id
                WHERE wc.sales_order_id = ? AND wc.status = 'posted'
                  AND NOT EXISTS (
                      SELECT 1 FROM sales_weight_inventory_allocations a
                      WHERE a.weight_card_line_id = wcl.id
                  )
                ORDER BY wc.id, wcl.id
                """,
                (int(order_id),),
            ).fetchall()
            for line in lines:
                remaining_quantity = float(line["quantity_pieces"])
                remaining_weight = float(line["allocated_weight_kg"])
                layers = connection.execute(
                    """
                    SELECT *, quantity_in - quantity_out AS available_quantity,
                              weight_in_kg - weight_out_kg AS available_weight
                    FROM finished_good_weight_layers
                    WHERE product_id = ? AND warehouse_id = ?
                      AND quantity_in - quantity_out > 0.0000001
                    ORDER BY id
                    """,
                    (int(line["product_id"]), int(order["warehouse_id"])),
                ).fetchall()
                for layer in layers:
                    if remaining_quantity <= EPSILON:
                        break
                    layer_qty = float(layer["available_quantity"])
                    take_qty = min(remaining_quantity, layer_qty)
                    target_weight = remaining_weight * take_qty / remaining_quantity
                    layer_weight = float(layer["available_weight"])
                    take_weight = min(target_weight, layer_weight)
                    if take_weight <= EPSILON:
                        continue
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
                            take_qty,
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
                        (take_qty, take_weight, int(layer["id"])),
                    )
                    remaining_quantity -= take_qty
                    remaining_weight -= take_weight

                if remaining_quantity > EPSILON or remaining_weight > EPSILON:
                    # Legacy finished stock may predate weight-layer tracking. Preserve
                    # the commercial actual weight without blocking delivery.
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

    @staticmethod
    def _reprice_order(connection, sales_order_id: int) -> None:
        active_total = float(
            connection.execute(
                """
                SELECT COALESCE(SUM(total_amount), 0) AS total
                FROM sales_weight_cards
                WHERE sales_order_id = ? AND status <> 'cancelled'
                """,
                (int(sales_order_id),),
            ).fetchone()["total"]
        )
        connection.execute(
            """
            UPDATE sales_orders
            SET billing_method = CASE WHEN ? > 0 THEN 'weight' ELSE 'piece' END,
                weight_card_total = ?
            WHERE id = ?
            """,
            (active_total, active_total, int(sales_order_id)),
        )
        order_lines = connection.execute(
            "SELECT id, quantity FROM sales_order_lines WHERE sales_order_id = ?",
            (int(sales_order_id),),
        ).fetchall()
        for line in order_lines:
            totals = connection.execute(
                """
                SELECT COALESCE(SUM(wcl.allocated_weight_kg), 0) AS weight,
                       COALESCE(SUM(wcl.line_total), 0) AS total
                FROM sales_weight_card_lines wcl
                JOIN sales_weight_cards wc ON wc.id = wcl.weight_card_id
                WHERE wcl.sales_order_line_id = ? AND wc.status <> 'cancelled'
                """,
                (int(line["id"]),),
            ).fetchone()
            weight = float(totals["weight"] or 0)
            total = float(totals["total"] or 0)
            quantity = float(line["quantity"] or 0)
            effective_piece_price = total / quantity if quantity > EPSILON else 0
            effective_kg_price = total / weight if weight > EPSILON else 0
            connection.execute(
                """
                UPDATE sales_order_lines
                SET billing_weight_kg = ?, price_per_kg = ?,
                    unit_price = ?, line_total = ?
                WHERE id = ?
                """,
                (
                    weight,
                    effective_kg_price,
                    effective_piece_price,
                    total,
                    int(line["id"]),
                ),
            )
        connection.execute(
            """
            UPDATE sales_invoices
            SET total = ?
            WHERE sales_order_id = ? AND status = 'draft'
            """,
            (active_total, int(sales_order_id)),
        )


__all__ = ["WeightSalesRepository"]
