from app.repositories.scrap_aware_manufacturing_repository import (
    ScrapAwareManufacturingRepository,
)


EPSILON = 0.0000001


class BaseMaterialScrapCostRepository(ScrapAwareManufacturingRepository):
    """Value new manufacturing scrap from base recipe materials only.

    Used scrap remains part of the manufacturing order's total material cost, but it does
    not dilute the unit cost assigned to newly produced scrap.
    """

    def list_orders(self) -> list[dict]:
        rows = super().list_orders()
        scrap_rows = self.database.fetch_all(
            """
            SELECT mo.id AS order_id, mo.returned_scrap_quantity,
                   COALESCE((
                       SELECT im.unit_cost
                       FROM inventory_moves im
                       WHERE im.reference_type = 'manufacturing_scrap'
                         AND im.reference_id = mo.id
                         AND im.quantity_in > 0
                       ORDER BY im.id DESC
                       LIMIT 1
                   ), 0) AS scrap_unit_cost
            FROM manufacturing_orders mo
            """
        )
        scrap_data = {
            int(row["order_id"]): {
                "returned_scrap_quantity": float(row["returned_scrap_quantity"] or 0),
                "scrap_unit_cost": float(row["scrap_unit_cost"] or 0),
            }
            for row in scrap_rows
        }
        for row in rows:
            row.update(
                scrap_data.get(
                    int(row["id"]),
                    {"returned_scrap_quantity": 0.0, "scrap_unit_cost": 0.0},
                )
            )
        return rows

    def complete_order_with_batches(
        self,
        order_id: int,
        *,
        actual_batches: int,
        actual_outputs: dict[int, float],
        returned_scrap_quantity: float,
    ) -> dict:
        order = self.get_order(order_id)
        if order["status"] != "in_progress":
            raise ValueError("يمكن إتمام أمر تصنيع جارٍ فقط")

        current_batches = int(order["actual_batches"])
        actual_batches = int(actual_batches)
        if actual_batches < current_batches:
            raise ValueError(
                f"عدد الخلطات الفعلي لا يمكن أن يقل عن الخلطات المصروفة ({current_batches})"
            )

        if actual_batches > current_batches:
            shortages = self.blocking_shortages(
                self.material_availability(
                    order_id,
                    target_batches=actual_batches,
                    additional_only=True,
                )
            )
            if shortages:
                raise ValueError("الخامات غير كافية لصرف الخلطات الإضافية")
            for _ in range(actual_batches - current_batches):
                super().add_batch(order_id)

        return self.complete_order(
            order_id,
            actual_outputs=actual_outputs,
            returned_scrap_quantity=returned_scrap_quantity,
        )

    def complete_order(
        self,
        order_id: int,
        *,
        actual_outputs: dict[int, float],
        returned_scrap_quantity: float = 0,
    ) -> dict:
        returned_scrap_quantity = float(returned_scrap_quantity or 0)
        if returned_scrap_quantity < 0:
            raise ValueError("كمية الكسر المرتجع لا يمكن أن تكون سالبة")

        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                """
                SELECT mo.*, r.scrap_product_id
                FROM manufacturing_orders mo
                JOIN manufacturing_recipes r ON r.id = mo.recipe_id
                WHERE mo.id = ?
                """,
                (order_id,),
            ).fetchone()
            if order is None or order["status"] != "in_progress":
                raise ValueError("يمكن إتمام أمر تصنيع جارٍ فقط")

            outputs = connection.execute(
                "SELECT * FROM manufacturing_order_outputs WHERE manufacturing_order_id = ?",
                (order_id,),
            ).fetchall()
            good_weight = 0.0
            normalized_actual: dict[int, float] = {}
            for output in outputs:
                product_id = int(output["product_id"])
                quantity = float(actual_outputs.get(product_id, 0) or 0)
                if quantity < 0:
                    raise ValueError("عدد المواسير الفعلي لا يمكن أن يكون سالبًا")
                normalized_actual[product_id] = quantity
                good_weight += quantity * float(output["standard_weight_kg"])
            if good_weight <= 0:
                raise ValueError("أدخل إنتاجًا سليمًا واحدًا على الأقل")

            materials = connection.execute(
                "SELECT * FROM manufacturing_order_materials WHERE manufacturing_order_id = ?",
                (order_id,),
            ).fetchall()
            input_weight = sum(float(row["actual_quantity"]) for row in materials)
            material_cost = sum(float(row["total_cost"]) for row in materials)
            if returned_scrap_quantity - input_weight > EPSILON:
                raise ValueError("الكسر المرتجع لا يمكن أن يتجاوز وزن الخامات المصروفة")

            base_materials = [
                row for row in materials if str(row["component_kind"]) == "material"
            ]
            base_material_weight = sum(
                float(row["actual_quantity"]) for row in base_materials
            )
            base_material_cost = sum(float(row["total_cost"]) for row in base_materials)
            if base_material_weight <= EPSILON:
                raise ValueError("لا يمكن حساب تكلفة الكسر بدون خامات أساسية مصروفة")

            scrap_unit_cost = base_material_cost / base_material_weight
            scrap_value = returned_scrap_quantity * scrap_unit_cost
            finished_cost = max(0.0, material_cost - scrap_value)
            finished_cost_per_kg = finished_cost / good_weight

            for output in outputs:
                product_id = int(output["product_id"])
                quantity = normalized_actual[product_id]
                unit_cost = finished_cost_per_kg * float(output["standard_weight_kg"])
                connection.execute(
                    """
                    UPDATE manufacturing_order_outputs
                    SET actual_quantity = ?, unit_cost = ? WHERE id = ?
                    """,
                    (quantity, unit_cost, output["id"]),
                )
                if quantity <= 0:
                    continue
                lot_number = f"{order['order_number']}-FG-{product_id}"
                lot_id = self._ensure_lot(connection, product_id, lot_number, unit_cost)
                connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing', ?, ?)
                    """,
                    (
                        product_id,
                        order["warehouse_id"],
                        lot_id,
                        quantity,
                        unit_cost,
                        order_id,
                        f"إنتاج تام {order['order_number']}",
                    ),
                )

            scrap_product_id = int(order["scrap_product_id"])
            if returned_scrap_quantity > 0:
                scrap_lot = f"{order['order_number']}-SCRAP"
                lot_id = self._ensure_lot(
                    connection, scrap_product_id, scrap_lot, scrap_unit_cost
                )
                connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing_scrap', ?, ?)
                    """,
                    (
                        scrap_product_id,
                        order["warehouse_id"],
                        lot_id,
                        returned_scrap_quantity,
                        scrap_unit_cost,
                        order_id,
                        f"كسر مصنع ناتج من {order['order_number']}",
                    ),
                )

            variance = input_weight - good_weight - returned_scrap_quantity
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET status = 'completed', returned_scrap_quantity = ?,
                    material_cost = ?, finished_cost = ?, weight_variance = ?,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    returned_scrap_quantity,
                    material_cost,
                    finished_cost,
                    variance,
                    order_id,
                ),
            )
            return {
                "material_cost": material_cost,
                "finished_cost": finished_cost,
                "scrap_unit_cost": scrap_unit_cost,
                "weight_variance": variance,
            }


__all__ = ["BaseMaterialScrapCostRepository"]
