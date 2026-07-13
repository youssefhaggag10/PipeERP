from app.database.connection import Database
from app.services.inventory_costing_service import InventoryCostingService
from app.services.manufacturing_planning_service import (
    ProductionTarget,
    calculate_batch_plan,
)


class ManufacturingRepository:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.costing = InventoryCostingService()

    def create_recipe(
        self,
        *,
        code: str,
        name: str,
        output_product_ids: list[int],
        components: list[dict],
        suggested_scrap_per_batch: float = 0,
        notes: str = "",
    ) -> int:
        code = code.strip().upper()
        name = name.strip()
        output_product_ids = list(dict.fromkeys(int(value) for value in output_product_ids))
        suggested_scrap_per_batch = float(suggested_scrap_per_batch or 0)
        if not code or not name:
            raise ValueError("كود واسم الخلطة مطلوبان")
        if not output_product_ids:
            raise ValueError("اربط الخلطة بمنتج نهائي واحد على الأقل")
        if not components:
            raise ValueError("أضف خامة واحدة على الأقل للخلطة")
        if suggested_scrap_per_batch < 0:
            raise ValueError("كمية الكسر المقترحة لا يمكن أن تكون سالبة")

        normalized_components: list[tuple[int, float]] = []
        for index, component in enumerate(components, start=1):
            product_id = int(component["product_id"])
            quantity = float(component["quantity_per_batch"])
            if quantity <= 0:
                raise ValueError(f"كمية خامة الخلطة رقم {index} يجب أن تكون أكبر من صفر")
            normalized_components.append((product_id, quantity))

        with self.database.session(immediate=True) as connection:
            placeholders = ",".join("?" for _ in output_product_ids)
            outputs = connection.execute(
                f"""
                SELECT id, standard_weight_kg FROM products
                WHERE id IN ({placeholders}) AND product_type = 'finished_good'
                  AND is_active = 1
                """,
                tuple(output_product_ids),
            ).fetchall()
            if len(outputs) != len(output_product_ids):
                raise ValueError("أحد المنتجات النهائية غير موجود أو غير نشط")
            if any(float(row["standard_weight_kg"]) <= 0 for row in outputs):
                raise ValueError("سجل الوزن القياسي لكل منتج نهائي قبل ربطه بالخلطة")

            for product_id, _ in normalized_components:
                product = connection.execute(
                    """
                    SELECT id FROM products
                    WHERE id = ? AND product_type IN ('raw_material', 'waste')
                      AND is_active = 1
                    """,
                    (product_id,),
                ).fetchone()
                if product is None:
                    raise ValueError("خامات الخلطة يجب أن تكون خامات أو كسر مصنع نشط")

            scrap_code = f"SCRAP-{code}"
            scrap = connection.execute(
                "SELECT id FROM products WHERE code = ?", (scrap_code,)
            ).fetchone()
            if scrap is None:
                scrap_cursor = connection.execute(
                    """
                    INSERT INTO products(code, name, product_type, unit, track_lots)
                    VALUES (?, ?, 'waste', 'كجم', 1)
                    """,
                    (scrap_code, f"كسر مصنع - {name}"),
                )
                scrap_product_id = int(scrap_cursor.lastrowid)
            else:
                scrap_product_id = int(scrap["id"])

            cursor = connection.execute(
                """
                INSERT INTO manufacturing_recipes(code, name, scrap_product_id, notes)
                VALUES (?, ?, ?, ?)
                """,
                (code, name, scrap_product_id, notes.strip()),
            )
            recipe_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO manufacturing_recipe_outputs(recipe_id, product_id)
                VALUES (?, ?)
                """,
                [(recipe_id, product_id) for product_id in output_product_ids],
            )
            connection.executemany(
                """
                INSERT INTO manufacturing_recipe_components(
                    recipe_id, product_id, component_kind,
                    quantity_per_batch, display_order
                ) VALUES (?, ?, 'material', ?, ?)
                """,
                [
                    (recipe_id, product_id, quantity, index)
                    for index, (product_id, quantity) in enumerate(
                        normalized_components, start=1
                    )
                ],
            )
            if suggested_scrap_per_batch > 0:
                connection.execute(
                    """
                    INSERT INTO manufacturing_recipe_components(
                        recipe_id, product_id, component_kind,
                        quantity_per_batch, display_order
                    ) VALUES (?, NULL, 'optional_scrap', ?, ?)
                    """,
                    (recipe_id, suggested_scrap_per_batch, len(components) + 1),
                )
            return recipe_id

    def list_recipes(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT r.id, r.code, r.name, r.notes, r.scrap_product_id,
                   COALESCE((
                       SELECT SUM(c.quantity_per_batch)
                       FROM manufacturing_recipe_components c
                       WHERE c.recipe_id = r.id AND c.component_kind = 'material'
                   ), 0) AS base_batch_weight,
                   COALESCE((
                       SELECT SUM(c.quantity_per_batch)
                       FROM manufacturing_recipe_components c
                       WHERE c.recipe_id = r.id AND c.component_kind = 'optional_scrap'
                   ), 0) AS suggested_scrap_per_batch,
                   COALESCE((
                       SELECT GROUP_CONCAT(p.name, '، ')
                       FROM manufacturing_recipe_outputs ro
                       JOIN products p ON p.id = ro.product_id
                       WHERE ro.recipe_id = r.id
                   ), '') AS output_summary
            FROM manufacturing_recipes r
            WHERE r.is_active = 1
            ORDER BY r.id DESC
            """
        )
        return [dict(row) for row in rows]

    def get_recipe(self, recipe_id: int) -> dict:
        recipe = self.database.fetch_one(
            "SELECT * FROM manufacturing_recipes WHERE id = ? AND is_active = 1",
            (recipe_id,),
        )
        if recipe is None:
            raise ValueError("الخلطة غير موجودة")
        result = dict(recipe)
        result["outputs"] = [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT p.id AS product_id, p.code, p.name, p.standard_weight_kg
                FROM manufacturing_recipe_outputs ro
                JOIN products p ON p.id = ro.product_id
                WHERE ro.recipe_id = ? AND p.is_active = 1
                ORDER BY p.name
                """,
                (recipe_id,),
            )
        ]
        result["components"] = [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT c.id, c.product_id, c.component_kind,
                       c.quantity_per_batch, COALESCE(p.code, '') AS code,
                       COALESCE(p.name, 'كسر مصنع اختياري') AS name
                FROM manufacturing_recipe_components c
                LEFT JOIN products p ON p.id = c.product_id
                WHERE c.recipe_id = ?
                ORDER BY c.display_order, c.id
                """,
                (recipe_id,),
            )
        ]
        return result

    def list_scrap_stock(self, warehouse_id: int) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT p.id AS product_id, p.code, p.name,
                   COALESCE(SUM(im.quantity_in - im.quantity_out), 0) AS available
            FROM products p
            LEFT JOIN inventory_moves im
              ON im.product_id = p.id AND im.warehouse_id = ?
            WHERE p.product_type = 'waste' AND p.is_active = 1
            GROUP BY p.id, p.code, p.name
            HAVING available > 0.0000001
            ORDER BY p.name
            """,
            (warehouse_id,),
        )
        return [dict(row) for row in rows]

    def create_order(
        self,
        *,
        recipe_id: int,
        warehouse_id: int,
        outputs: list[dict],
        scrap_inputs: list[dict] | None = None,
        notes: str = "",
    ) -> int:
        recipe = self.get_recipe(recipe_id)
        allowed_outputs = {int(row["product_id"]): row for row in recipe["outputs"]}
        targets: list[ProductionTarget] = []
        normalized_outputs: list[dict] = []
        for line in outputs:
            product_id = int(line["product_id"])
            quantity = float(line["quantity"])
            if product_id not in allowed_outputs:
                raise ValueError("المنتج النهائي غير مرتبط بالخلطة المختارة")
            weight = float(allowed_outputs[product_id]["standard_weight_kg"])
            targets.append(ProductionTarget(product_id, quantity, weight))
            normalized_outputs.append(
                {"product_id": product_id, "quantity": quantity, "weight": weight}
            )

        material_components = [
            row for row in recipe["components"] if row["component_kind"] == "material"
        ]
        normalized_scrap: list[dict] = []
        for line in scrap_inputs or []:
            quantity_per_batch = float(line["quantity_per_batch"])
            if quantity_per_batch <= 0:
                raise ValueError("كمية الكسر في الخلطة يجب أن تكون أكبر من صفر")
            normalized_scrap.append(
                {
                    "product_id": int(line["product_id"]),
                    "quantity_per_batch": quantity_per_batch,
                }
            )

        plan = calculate_batch_plan(
            targets,
            [float(row["quantity_per_batch"]) for row in material_components],
            [row["quantity_per_batch"] for row in normalized_scrap],
        )
        with self.database.session(immediate=True) as connection:
            warehouse = connection.execute(
                "SELECT id FROM warehouses WHERE id = ? AND is_active = 1", (warehouse_id,)
            ).fetchone()
            if warehouse is None:
                raise ValueError("المخزن غير موجود أو غير نشط")
            for scrap in normalized_scrap:
                row = connection.execute(
                    """
                    SELECT id FROM products
                    WHERE id = ? AND product_type = 'waste' AND is_active = 1
                    """,
                    (scrap["product_id"],),
                ).fetchone()
                if row is None:
                    raise ValueError("مصدر كسر المصنع غير موجود")

            next_id = int(
                connection.execute(
                    "SELECT COALESCE(MAX(id), 0) + 1 FROM manufacturing_orders"
                ).fetchone()[0]
            )
            order_number = f"MO{next_id:05d}"
            cursor = connection.execute(
                """
                INSERT INTO manufacturing_orders(
                    order_number, recipe_id, warehouse_id, planned_batches, notes
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (order_number, recipe_id, warehouse_id, plan.batches, notes.strip()),
            )
            order_id = int(cursor.lastrowid)
            connection.executemany(
                """
                INSERT INTO manufacturing_order_outputs(
                    manufacturing_order_id, product_id, planned_quantity,
                    standard_weight_kg
                ) VALUES (?, ?, ?, ?)
                """,
                [
                    (order_id, row["product_id"], row["quantity"], row["weight"])
                    for row in normalized_outputs
                ],
            )
            connection.executemany(
                """
                INSERT INTO manufacturing_order_materials(
                    manufacturing_order_id, product_id, component_kind,
                    quantity_per_batch, planned_quantity
                ) VALUES (?, ?, 'material', ?, ?)
                """,
                [
                    (
                        order_id,
                        int(row["product_id"]),
                        float(row["quantity_per_batch"]),
                        float(row["quantity_per_batch"]) * plan.batches,
                    )
                    for row in material_components
                ],
            )
            connection.executemany(
                """
                INSERT INTO manufacturing_order_materials(
                    manufacturing_order_id, product_id, component_kind,
                    quantity_per_batch, planned_quantity
                ) VALUES (?, ?, 'scrap', ?, ?)
                """,
                [
                    (
                        order_id,
                        row["product_id"],
                        row["quantity_per_batch"],
                        row["quantity_per_batch"] * plan.batches,
                    )
                    for row in normalized_scrap
                ],
            )
            return order_id

    def list_orders(self) -> list[dict]:
        rows = self.database.fetch_all(
            """
            SELECT mo.id, mo.order_number, mo.created_at, mo.status,
                   mo.planned_batches, mo.actual_batches, mo.material_cost,
                   mo.finished_cost, mo.weight_variance, r.name AS recipe_name,
                   COALESCE((
                       SELECT GROUP_CONCAT(p.name || ' × ' || moo.planned_quantity, '، ')
                       FROM manufacturing_order_outputs moo
                       JOIN products p ON p.id = moo.product_id
                       WHERE moo.manufacturing_order_id = mo.id
                   ), '') AS output_summary
            FROM manufacturing_orders mo
            JOIN manufacturing_recipes r ON r.id = mo.recipe_id
            ORDER BY mo.id DESC
            """
        )
        return [dict(row) for row in rows]

    def get_order(self, order_id: int) -> dict:
        order = self.database.fetch_one(
            """
            SELECT mo.*, r.name AS recipe_name, r.scrap_product_id
            FROM manufacturing_orders mo
            JOIN manufacturing_recipes r ON r.id = mo.recipe_id
            WHERE mo.id = ?
            """,
            (order_id,),
        )
        if order is None:
            raise ValueError("أمر التصنيع غير موجود")
        result = dict(order)
        result["outputs"] = [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT moo.*, p.code, p.name
                FROM manufacturing_order_outputs moo
                JOIN products p ON p.id = moo.product_id
                WHERE moo.manufacturing_order_id = ? ORDER BY moo.id
                """,
                (order_id,),
            )
        ]
        result["materials"] = [
            dict(row)
            for row in self.database.fetch_all(
                """
                SELECT mom.*, p.code, p.name
                FROM manufacturing_order_materials mom
                JOIN products p ON p.id = mom.product_id
                WHERE mom.manufacturing_order_id = ? ORDER BY mom.id
                """,
                (order_id,),
            )
        ]
        return result

    def start_order(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT * FROM manufacturing_orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            if order["status"] != "draft":
                raise ValueError("يمكن بدء أمر التصنيع من حالة المسودة فقط")
            materials = connection.execute(
                "SELECT * FROM manufacturing_order_materials WHERE manufacturing_order_id = ?",
                (order_id,),
            ).fetchall()
            for material in materials:
                quantity = float(material["planned_quantity"])
                if material["component_kind"] == "scrap":
                    quantity = min(
                        quantity,
                        self.costing.available_quantity(
                            connection,
                            int(material["product_id"]),
                            int(order["warehouse_id"]),
                        ),
                    )
                self._issue_material(
                    connection,
                    order_id=order_id,
                    warehouse_id=int(order["warehouse_id"]),
                    material_id=int(material["id"]),
                    product_id=int(material["product_id"]),
                    quantity=quantity,
                )
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET status = 'in_progress', actual_batches = planned_batches,
                    started_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (order_id,),
            )
            self._refresh_material_cost(connection, order_id)

    def add_batch(self, order_id: int) -> None:
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT * FROM manufacturing_orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None or order["status"] != "in_progress":
                raise ValueError("أضف خلطة فقط لأمر تصنيع جارٍ")
            materials = connection.execute(
                "SELECT * FROM manufacturing_order_materials WHERE manufacturing_order_id = ?",
                (order_id,),
            ).fetchall()
            for material in materials:
                quantity = float(material["quantity_per_batch"])
                if material["component_kind"] == "scrap":
                    quantity = min(
                        quantity,
                        self.costing.available_quantity(
                            connection,
                            int(material["product_id"]),
                            int(order["warehouse_id"]),
                        ),
                    )
                self._issue_material(
                    connection,
                    order_id=order_id,
                    warehouse_id=int(order["warehouse_id"]),
                    material_id=int(material["id"]),
                    product_id=int(material["product_id"]),
                    quantity=quantity,
                )
            connection.execute(
                "UPDATE manufacturing_orders SET actual_batches = actual_batches + 1 WHERE id = ?",
                (order_id,),
            )
            self._refresh_material_cost(connection, order_id)

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
            if returned_scrap_quantity - input_weight > 0.0000001:
                raise ValueError("الكسر المرتجع لا يمكن أن يتجاوز وزن الخامات المصروفة")
            average_input_cost = material_cost / input_weight if input_weight else 0.0
            scrap_value = returned_scrap_quantity * average_input_cost
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
                        product_id, order["warehouse_id"], lot_id, quantity,
                        unit_cost, order_id, f"إنتاج تام {order['order_number']}",
                    ),
                )

            scrap_product_id = int(order["scrap_product_id"])
            if returned_scrap_quantity > 0:
                scrap_lot = f"{order['order_number']}-SCRAP"
                lot_id = self._ensure_lot(
                    connection, scrap_product_id, scrap_lot, average_input_cost
                )
                connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing_scrap', ?, ?)
                    """,
                    (
                        scrap_product_id, order["warehouse_id"], lot_id,
                        returned_scrap_quantity, average_input_cost, order_id,
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
                    returned_scrap_quantity, material_cost, finished_cost,
                    variance, order_id,
                ),
            )
            return {
                "material_cost": material_cost,
                "finished_cost": finished_cost,
                "scrap_unit_cost": average_input_cost,
                "weight_variance": variance,
            }

    def _issue_material(
        self,
        connection,
        *,
        order_id: int,
        warehouse_id: int,
        material_id: int,
        product_id: int,
        quantity: float,
    ) -> None:
        if quantity <= 0:
            return
        move_ids = self.costing.post_issue(
            connection,
            product_id=product_id,
            warehouse_id=warehouse_id,
            quantity=quantity,
            reference_type="manufacturing",
            reference_id=order_id,
            notes=f"صرف لأمر تصنيع رقم {order_id}",
        )
        placeholders = ",".join("?" for _ in move_ids)
        row = connection.execute(
            f"""
            SELECT SUM(quantity_out * unit_cost) AS total_cost,
                   SUM(quantity_out) AS quantity
            FROM inventory_moves WHERE id IN ({placeholders})
            """,
            tuple(move_ids),
        ).fetchone()
        issued_quantity = float(row["quantity"] or 0)
        issued_cost = float(row["total_cost"] or 0)
        connection.execute(
            """
            UPDATE manufacturing_order_materials
            SET actual_quantity = actual_quantity + ?,
                total_cost = total_cost + ?,
                unit_cost = CASE
                    WHEN actual_quantity + ? > 0
                    THEN (total_cost + ?) / (actual_quantity + ?)
                    ELSE 0 END
            WHERE id = ?
            """,
            (
                issued_quantity, issued_cost, issued_quantity, issued_cost,
                issued_quantity, material_id,
            ),
        )

    @staticmethod
    def _ensure_lot(connection, product_id: int, lot_number: str, unit_cost: float) -> int:
        row = connection.execute(
            "SELECT id FROM lots WHERE product_id = ? AND lot_number = ?",
            (product_id, lot_number),
        ).fetchone()
        if row is not None:
            return int(row["id"])
        cursor = connection.execute(
            "INSERT INTO lots(product_id, lot_number, unit_cost) VALUES (?, ?, ?)",
            (product_id, lot_number, unit_cost),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _refresh_material_cost(connection, order_id: int) -> None:
        connection.execute(
            """
            UPDATE manufacturing_orders
            SET material_cost = COALESCE((
                SELECT SUM(total_cost) FROM manufacturing_order_materials
                WHERE manufacturing_order_id = ?
            ), 0)
            WHERE id = ?
            """,
            (order_id, order_id),
        )
