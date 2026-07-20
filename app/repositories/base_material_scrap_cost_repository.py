from app.repositories.scrap_aware_manufacturing_repository import (
    ScrapAwareManufacturingRepository,
)

EPSILON = 0.0000001


class BaseMaterialScrapCostRepository(ScrapAwareManufacturingRepository):
    """Dynamic manufacturing scrap costing based on actual weighted inputs.

    A recipe keeps an estimated scrap cost based on the current costs of its base
    materials. A completed manufacturing order values newly produced scrap using
    the weighted average cost of every kilogram actually issued to that order,
    including reused scrap.
    """

    def __init__(self, database) -> None:
        super().__init__(database)
        self._ensure_recipe_cost_schema()

    def _ensure_recipe_cost_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(manufacturing_recipes)").fetchall()
            }
            if "estimated_scrap_unit_cost" not in columns:
                connection.execute(
                    "ALTER TABLE manufacturing_recipes "
                    "ADD COLUMN estimated_scrap_unit_cost REAL NOT NULL DEFAULT 0"
                )

    @staticmethod
    def _remaining_inventory_unit_cost(connection, product_id: int) -> float:
        row = connection.execute(
            """
            SELECT
                COALESCE(SUM(
                    (source.quantity_in - COALESCE(used.allocated, 0))
                    * source.unit_cost
                ), 0) AS remaining_value,
                COALESCE(SUM(
                    source.quantity_in - COALESCE(used.allocated, 0)
                ), 0) AS remaining_quantity
            FROM inventory_moves source
            LEFT JOIN (
                SELECT source_move_id, SUM(quantity) AS allocated
                FROM inventory_cost_allocations
                GROUP BY source_move_id
            ) used ON used.source_move_id = source.id
            WHERE source.product_id = ?
              AND source.quantity_in > 0
              AND source.quantity_in - COALESCE(used.allocated, 0) > ?
            """,
            (int(product_id), EPSILON),
        ).fetchone()
        quantity = float(row["remaining_quantity"] or 0)
        if quantity > EPSILON:
            return float(row["remaining_value"] or 0) / quantity

        latest = connection.execute(
            """
            SELECT unit_cost
            FROM inventory_moves
            WHERE product_id = ? AND quantity_in > 0
            ORDER BY move_date DESC, id DESC
            LIMIT 1
            """,
            (int(product_id),),
        ).fetchone()
        return float(latest["unit_cost"] or 0) if latest is not None else 0.0

    def _calculate_recipe_estimate(self, connection, recipe_id: int) -> float:
        components = connection.execute(
            """
            SELECT product_id, quantity_per_batch
            FROM manufacturing_recipe_components
            WHERE recipe_id = ? AND component_kind = 'material'
            ORDER BY display_order, id
            """,
            (int(recipe_id),),
        ).fetchall()
        total_weight = sum(float(row["quantity_per_batch"]) for row in components)
        if total_weight <= EPSILON:
            return 0.0
        total_cost = sum(
            float(row["quantity_per_batch"])
            * self._remaining_inventory_unit_cost(connection, int(row["product_id"]))
            for row in components
        )
        return total_cost / total_weight

    def _refresh_recipe_estimate(self, recipe_id: int) -> float:
        with self.database.session(immediate=True) as connection:
            estimate = self._calculate_recipe_estimate(connection, int(recipe_id))
            connection.execute(
                """
                UPDATE manufacturing_recipes
                SET estimated_scrap_unit_cost = ?
                WHERE id = ?
                """,
                (estimate, int(recipe_id)),
            )
            return estimate

    def _refresh_all_recipe_estimates(self) -> None:
        with self.database.session(immediate=True) as connection:
            recipe_ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM manufacturing_recipes WHERE is_active = 1"
                ).fetchall()
            ]
            for recipe_id in recipe_ids:
                estimate = self._calculate_recipe_estimate(connection, recipe_id)
                connection.execute(
                    """
                    UPDATE manufacturing_recipes
                    SET estimated_scrap_unit_cost = ?
                    WHERE id = ?
                    """,
                    (estimate, recipe_id),
                )

    def create_recipe(self, **kwargs) -> int:
        recipe_id = super().create_recipe(**kwargs)
        self._refresh_recipe_estimate(recipe_id)
        return recipe_id

    def update_recipe(self, recipe_id: int, **kwargs) -> None:
        super().update_recipe(recipe_id, **kwargs)
        self._refresh_recipe_estimate(recipe_id)

    def list_recipes(self) -> list[dict]:
        self._refresh_all_recipe_estimates()
        rows = super().list_recipes()
        estimates = {
            int(row["id"]): float(row["estimated_scrap_unit_cost"] or 0)
            for row in self.database.fetch_all(
                """
                SELECT id, estimated_scrap_unit_cost
                FROM manufacturing_recipes
                WHERE is_active = 1
                """
            )
        }
        for row in rows:
            row["estimated_scrap_unit_cost"] = estimates.get(int(row["id"]), 0.0)
        return rows

    def get_recipe(self, recipe_id: int) -> dict:
        estimate = self._refresh_recipe_estimate(recipe_id)
        result = super().get_recipe(recipe_id)
        result["estimated_scrap_unit_cost"] = estimate
        return result

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
            if input_weight <= EPSILON:
                raise ValueError("لا يمكن حساب تكلفة الكسر بدون خامات مصروفة")

            scrap_unit_cost = material_cost / input_weight
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
                    connection,
                    scrap_product_id,
                    scrap_lot,
                    scrap_unit_cost,
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
