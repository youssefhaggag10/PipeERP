from __future__ import annotations

from app.repositories.weight_sales_repository import WeightSalesRepository


class StandaloneWeightSalesRepository(WeightSalesRepository):
    """Weight-card sales that create their own internal order automatically."""

    def create_weight_sale(
        self,
        *,
        customer_id: int,
        lines: list[dict],
        net_weight_kg: float,
        price_per_kg: float,
        card_number: str = "",
        vehicle_number: str = "",
        gross_weight_kg: float | None = None,
        tare_weight_kg: float | None = None,
        notes: str = "",
    ) -> dict:
        normalized_lines = [
            {
                "product_id": int(line["product_id"]),
                "quantity": float(line["quantity"]),
                "unit": str(line.get("unit", "") or "ماسورة"),
                "unit_price": 0.0,
            }
            for line in lines
        ]
        order_id = self.create_order_with_lines(
            customer_id=int(customer_id),
            lines=normalized_lines,
            notes=notes,
            paid_amount=0,
        )
        try:
            order_lines = self.database.fetch_all(
                """
                SELECT id, product_id, quantity
                FROM sales_order_lines
                WHERE sales_order_id = ?
                ORDER BY id
                """,
                (int(order_id),),
            )
            if len(order_lines) != len(normalized_lines):
                raise ValueError("تعذر تجهيز بنود كارتة الوزن")
            card_lines = [
                {
                    "sales_order_line_id": int(row["id"]),
                    "quantity_pieces": float(row["quantity"]),
                }
                for row in order_lines
            ]
            card_id = self.create_weight_card(
                int(order_id),
                lines=card_lines,
                net_weight_kg=float(net_weight_kg),
                price_per_kg=float(price_per_kg),
                card_number=card_number,
                vehicle_number=vehicle_number,
                gross_weight_kg=gross_weight_kg,
                tare_weight_kg=tare_weight_kg,
                notes=notes,
            )
        except Exception:
            with self.database.session(immediate=True) as connection:
                connection.execute(
                    "DELETE FROM sales_order_lines WHERE sales_order_id = ?",
                    (int(order_id),),
                )
                connection.execute(
                    "DELETE FROM sales_orders WHERE id = ? AND status = 'draft'",
                    (int(order_id),),
                )
            raise
        return {"order_id": int(order_id), "card_id": int(card_id)}

    def list_weight_sales(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT so.id AS order_id, so.order_number, so.order_date, so.status,
                   p.name AS customer_name, w.name AS warehouse_name,
                   wc.id AS card_id, wc.card_number, wc.vehicle_number,
                   wc.net_weight_kg, wc.price_per_kg, wc.total_amount,
                   wc.status AS card_status, wc.notes,
                   COALESCE(SUM(wcl.quantity_pieces), 0) AS total_pieces,
                   COUNT(DISTINCT wcl.product_id) AS product_count
            FROM sales_orders so
            JOIN partners p ON p.id = so.customer_id
            JOIN warehouses w ON w.id = so.warehouse_id
            JOIN sales_weight_cards wc
              ON wc.sales_order_id = so.id AND wc.status <> 'cancelled'
            LEFT JOIN sales_weight_card_lines wcl ON wcl.weight_card_id = wc.id
            WHERE so.billing_method = 'weight'
            GROUP BY so.id, so.order_number, so.order_date, so.status,
                     p.name, w.name, wc.id, wc.card_number, wc.vehicle_number,
                     wc.net_weight_kg, wc.price_per_kg, wc.total_amount,
                     wc.status, wc.notes
            ORDER BY so.id DESC, wc.id DESC
            """
        )
        return [dict(row) for row in rows]

    def delete_draft_weight_sale(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT status FROM sales_orders WHERE id = ?",
                (int(order_id),),
            ).fetchone()
            if order is None:
                raise ValueError("بيع الوزن غير موجود")
            if str(order["status"]) != "draft":
                raise ValueError("لا يمكن حذف بيع وزن تم تسليمه")
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
                "DELETE FROM sales_invoices WHERE sales_order_id = ?",
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

    def deliver_weight_sale(self, order_id: int) -> None:
        self.deliver_order(int(order_id))


__all__ = ["StandaloneWeightSalesRepository"]
