from app.repositories.advanced_manufacturing_repository import AdvancedManufacturingRepository


EPSILON = 0.0000001


class ScrapAwareManufacturingRepository(AdvancedManufacturingRepository):
    """Replans draft orders from the scrap quantity that is actually available."""

    def replan_draft_for_available_scrap(self, order_id: int) -> dict:
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
        if target_weight <= 0 or base_batch_weight <= 0:
            raise ValueError("تعذر حساب وزن أمر التصنيع أو وزن الخلطة الأساسية")

        old_batches = int(order["planned_batches"])
        batches = max(1, old_batches)
        available_by_product: dict[int, float] = {}
        with self.database.session() as connection:
            for material in order["materials"]:
                if material["component_kind"] != "scrap":
                    continue
                product_id = int(material["product_id"])
                available_by_product[product_id] = self.costing.available_quantity(
                    connection, product_id, int(order["warehouse_id"])
                )

        def usable_scrap(batch_count: int) -> tuple[float, float]:
            planned = 0.0
            usable = 0.0
            for material in order["materials"]:
                if material["component_kind"] != "scrap":
                    continue
                product_id = int(material["product_id"])
                requested = float(material["quantity_per_batch"]) * batch_count
                planned += requested
                usable += min(requested, available_by_product.get(product_id, 0.0))
            return planned, usable

        planned_scrap, actual_scrap = usable_scrap(batches)
        input_weight = base_batch_weight * batches + actual_scrap
        while input_weight + EPSILON < target_weight:
            batches += 1
            if batches > 1_000_000:
                raise ValueError("تعذر حساب عدد خلطات صالح لأمر التصنيع")
            planned_scrap, actual_scrap = usable_scrap(batches)
            input_weight = base_batch_weight * batches + actual_scrap

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
            "planned_scrap": planned_scrap,
            "usable_scrap": actual_scrap,
            "planned_input_weight": input_weight,
            "expected_overage_weight": input_weight - target_weight,
        }


__all__ = ["ScrapAwareManufacturingRepository"]
