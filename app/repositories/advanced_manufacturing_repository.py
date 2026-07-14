from app.repositories.enhanced_manufacturing_repository import EnhancedManufacturingRepository
from app.services.manufacturing_planning_service import ProductionTarget, calculate_batch_plan


EPSILON = 0.0000001


class AdvancedManufacturingRepository(EnhancedManufacturingRepository):
    """Safer manufacturing workflow with availability checks and automatic replanning."""

    def replan_draft_for_available_scrap(self, order_id: int) -> dict:
        """Increase draft batches when optional scrap stock is below the planned amount.

        The smallest batch count is selected where fixed recipe materials plus the scrap
        that can actually be issued cover the requested finished-product weight.
        """
        order = self.get_order(order_id)
        if order["status"] != "draft":
            raise ValueError("يمكن إعادة تخطيط أمر التصنيع وهو مسودة فقط")

        target_weight = sum(
            float(row["planned_quantity"]) * float(row["standard_weight_kg"])
            for row in order["outputs"]
        )
        base_batch_weight = sum(
            float(row["quantity_per_batch"])
            for row in order["materials"]
            if row["component_kind"] == "material"
        )
        if target_weight <= 0:
            raise ValueError("أمر التصنيع لا يحتوي على وزن إنتاج مطلوب")
        if base_batch_weight <= 0:
            raise ValueError("الخلطة لا تحتوي على وزن خامات أساسية صالح")

        old_batches = int(order["planned_batches"])
        batches = max(1, old_batches)
        scrap_available: dict[int, float] = {}
        with self.database.session() as connection:
            for material in order["materials"]:
                if material["component_kind"] != "scrap":
                    continue
                product_id = int(material["product_id"])
                scrap_available[product_id] = self.costing.available_quantity(
                    connection, product_id, int(order["warehouse_id"])
                )

        def scrap_weights(batch_count: int) -> tuple[float, float]:
            planned = 0.0
            usable = 0.0
            for material in order["materials"]:
                if material["component_kind"] != "scrap":
                    continue
                product_id = int(material["product_id"])
                requested = float(material["quantity_per_batch"]) * batch_count
                planned += requested
                usable += min(requested, scrap_available.get(product_id, 0.0))
            return planned, usable

        max_batches = 1_000_000
        planned_scrap, usable_scrap = scrap_weights(batches)
        planned_input = base_batch_weight * batches + usable_scrap
        while planned_input + EPSILON < target_weight:
            batches += 1
            if batches > max_batches:
                raise ValueError("تعذر حساب عدد خلطات صالح لأمر التصنيع")
            planned_scrap, usable_scrap = scrap_weights(batches)
            planned_input = base_batch_weight * batches + usable_scrap

        changed = batches != old_batches
        if changed:
            with self.database.session(immediate=True) as connection:
                current = connection.execute(
                    "SELECT status FROM manufacturing_orders WHERE id = ?", (order_id,)
                ).fetchone()
                if current is None:
                    raise ValueError("أمر التصنيع غير موجود")
                if current["status"] != "draft":
                    raise ValueError("تغيرت حالة أمر التصنيع؛ أعد تحميل الشاشة")
                connection.execute(
                    "UPDATE manufacturing_orders SET planned_batches = ? WHERE id = ?",
                    (batches, order_id),
                )
                connection.execute(
                    """
                    UPDATE manufacturing_order_materials
                    SET planned_quantity = quantity_per_batch * ?
                    WHERE manufacturing_order_id = ?
                    """,
                    (batches, order_id),
                )

        return {
            "changed": changed,
            "old_batches": old_batches,
            "new_batches": batches,
            "target_weight": target_weight,
            "base_batch_weight": base_batch_weight,
            "planned_scrap": planned_scrap,
            "usable_scrap": usable_scrap,
            "planned_input_weight": planned_input,
            "expected_overage_weight": planned_input - target_weight,
        }

    def material_availability(
        self,
        order_id: int,
        *,
        target_batches: int | None = None,
        additional_only: bool = False,
    ) -> list[dict]:
        order = self.get_order(order_id)
        batches = int(
            target_batches if target_batches is not None else order["planned_batches"]
        )
        if batches < 0:
            raise ValueError("عدد الخلطات لا يمكن أن يكون سالبًا")
        current_batches = int(order["actual_batches"])
        requested_batches = max(0, batches - current_batches) if additional_only else batches

        rows: list[dict] = []
        with self.database.session() as connection:
            for material in order["materials"]:
                required = float(material["quantity_per_batch"]) * requested_batches
                available = self.costing.available_quantity(
                    connection,
                    int(material["product_id"]),
                    int(order["warehouse_id"]),
                )
                is_optional = str(material["component_kind"]) == "scrap"
                shortage = max(0.0, required - available)
                rows.append(
                    {
                        "product_id": int(material["product_id"]),
                        "code": str(material["code"]),
                        "name": str(material["name"]),
                        "component_kind": str(material["component_kind"]),
                        "required": required,
                        "available": available,
                        "will_issue": min(required, available) if is_optional else required,
                        "shortage": shortage,
                        "blocks_start": shortage > EPSILON and not is_optional,
                    }
                )
        return rows

    @staticmethod
    def blocking_shortages(rows: list[dict]) -> list[dict]:
        return [row for row in rows if bool(row.get("blocks_start"))]

    def update_draft_order(
        self,
        order_id: int,
        *,
        recipe_id: int,
        warehouse_id: int,
        outputs: list[dict],
        scrap_inputs: list[dict] | None = None,
        notes: str = "",
    ) -> None:
        recipe = self.get_recipe(recipe_id)
        allowed_outputs = {int(row["product_id"]): row for row in recipe["outputs"]}
        targets: list[ProductionTarget] = []
        normalized_outputs: list[dict] = []
        for line in outputs:
            product_id = int(line["product_id"])
            quantity = float(line["quantity"])
            if quantity <= 0:
                raise ValueError("عدد المواسير المطلوبة يجب أن يكون أكبر من صفر")
            if product_id not in allowed_outputs:
                raise ValueError("المنتج النهائي غير مرتبط بالخلطة المختارة")
            weight = float(allowed_outputs[product_id]["standard_weight_kg"])
            targets.append(ProductionTarget(product_id, quantity, weight))
            normalized_outputs.append(
                {"product_id": product_id, "quantity": quantity, "weight": weight}
            )
        if not normalized_outputs:
            raise ValueError("أضف مقاسًا واحدًا على الأقل")

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
            [float(row["quantity_per_batch"]) for row in normalized_scrap],
        )
        with self.database.session(immediate=True) as connection:
            order = connection.execute(
                "SELECT status FROM manufacturing_orders WHERE id = ?", (order_id,)
            ).fetchone()
            if order is None:
                raise ValueError("أمر التصنيع غير موجود")
            if order["status"] != "draft":
                raise ValueError("يمكن تعديل أمر التصنيع وهو مسودة فقط")
            warehouse = connection.execute(
                "SELECT id FROM warehouses WHERE id = ? AND is_active = 1",
                (warehouse_id,),
            ).fetchone()
            if warehouse is None:
                raise ValueError("المخزن غير موجود أو غير نشط")

            connection.execute(
                """
                UPDATE manufacturing_orders
                SET recipe_id = ?, warehouse_id = ?, planned_batches = ?, notes = ?
                WHERE id = ?
                """,
                (recipe_id, warehouse_id, plan.batches, notes.strip(), order_id),
            )
            connection.execute(
                "DELETE FROM manufacturing_order_outputs WHERE manufacturing_order_id = ?",
                (order_id,),
            )
            connection.execute(
                "DELETE FROM manufacturing_order_materials WHERE manufacturing_order_id = ?",
                (order_id,),
            )
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

    def start_order(self, order_id: int) -> None:
        self.replan_draft_for_available_scrap(order_id)
        shortages = self.blocking_shortages(self.material_availability(order_id))
        if shortages:
            raise ValueError("يوجد عجز في خامات أمر التصنيع")
        super().start_order(order_id)

    def suggested_scrap_quantity(
        self,
        order_id: int,
        *,
        actual_outputs: dict[int, float],
        target_batches: int,
    ) -> float:
        order = self.get_order(order_id)
        current_batches = int(order["actual_batches"])
        target_batches = int(target_batches)
        if target_batches < current_batches:
            raise ValueError(
                f"عدد الخلطات الفعلي لا يمكن أن يقل عن الخلطات المصروفة ({current_batches})"
            )

        input_weight = sum(float(row["actual_quantity"]) for row in order["materials"])
        extra_batches = target_batches - current_batches
        if extra_batches > 0:
            with self.database.session() as connection:
                for material in order["materials"]:
                    extra = float(material["quantity_per_batch"]) * extra_batches
                    if material["component_kind"] == "scrap":
                        available = self.costing.available_quantity(
                            connection,
                            int(material["product_id"]),
                            int(order["warehouse_id"]),
                        )
                        extra = min(extra, available)
                    input_weight += extra

        good_weight = 0.0
        for output in order["outputs"]:
            quantity = float(actual_outputs.get(int(output["product_id"]), 0) or 0)
            if quantity < 0:
                raise ValueError("عدد المواسير الفعلي لا يمكن أن يكون سالبًا")
            good_weight += quantity * float(output["standard_weight_kg"])
        return max(0.0, input_weight - good_weight)

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

        return super().complete_order(
            order_id,
            actual_outputs=actual_outputs,
            returned_scrap_quantity=returned_scrap_quantity,
        )


__all__ = ["AdvancedManufacturingRepository"]