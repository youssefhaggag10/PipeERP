from __future__ import annotations

import json

from app.database.completion_summary_schema import ensure_completion_summary_schema
from app.repositories.base_material_scrap_cost_repository import (
    BaseMaterialScrapCostRepository,
)
from app.repositories.production_run_repository import ProductionRunRepository

EPSILON = 0.0000001


class OrderCompletionManufacturingRepository(ProductionRunRepository):
    """Original one-time material issue with aggregate completion analytics."""

    def __init__(self, database) -> None:
        super().__init__(database)
        with self.database.session(immediate=True) as connection:
            ensure_completion_summary_schema(connection)

    def start_order(self, order_id: int) -> None:
        BaseMaterialScrapCostRepository.start_order(self, int(order_id))

    def complete_order_with_mix_summary(
        self,
        order_id: int,
        *,
        actual_batches: int,
        full_batches: int,
        modified_batches: int,
        outputs: dict[int, dict[str, float]],
        scrap_weight: float,
        notes: str,
        adjustments: list[dict],
    ) -> dict:
        actual_batches = int(actual_batches)
        full_batches = int(full_batches)
        modified_batches = int(modified_batches)
        scrap_weight = float(scrap_weight or 0)
        if actual_batches <= 0:
            raise ValueError("عدد الخلطات الفعلي يجب أن يكون أكبر من صفر")
        if min(full_batches, modified_batches) < 0:
            raise ValueError("أعداد الخلطات لا يمكن أن تكون سالبة")
        if full_batches + modified_batches != actual_batches:
            raise ValueError("الخلطات الكاملة والمعدلة يجب أن تساوي عدد الخلطات الفعلي")
        if scrap_weight < 0:
            raise ValueError("الهالك لا يمكن أن يكون سالبًا")

        with self.database.session(immediate=True) as connection:
            ensure_completion_summary_schema(connection)
            order = connection.execute(
                """
                SELECT mo.*, r.scrap_product_id
                FROM manufacturing_orders mo
                JOIN manufacturing_recipes r ON r.id = mo.recipe_id
                WHERE mo.id = ?
                """,
                (int(order_id),),
            ).fetchone()
            if order is None or str(order["status"]) != "in_progress":
                raise ValueError("يمكن إتمام أمر تصنيع جارٍ فقط")
            issued_batches = int(order["actual_batches"])
            if actual_batches > issued_batches:
                raise ValueError(
                    f"عدد الخلطات الفعلي لا يمكن أن يتجاوز الخلطات المصروفة ({issued_batches})"
                )

            materials = connection.execute(
                """
                SELECT mom.*, p.code, p.name
                FROM manufacturing_order_materials mom
                JOIN products p ON p.id = mom.product_id
                WHERE mom.manufacturing_order_id = ?
                ORDER BY mom.id
                """,
                (int(order_id),),
            ).fetchall()
            if not materials:
                raise ValueError("أمر التصنيع لا يحتوي على خامات مصروفة")
            material_by_id = {int(row["product_id"]): row for row in materials}

            adjustment_batches = sum(int(item.get("batch_count", 0) or 0) for item in adjustments)
            if modified_batches and adjustment_batches != modified_batches:
                raise ValueError(
                    "مجموع عدد الخلطات داخل جدول تعديلات الخلطات يجب أن يساوي الخلطات المعدلة"
                )
            if not modified_batches and adjustments:
                raise ValueError("احذف تعديلات الخلطات لأن عدد الخلطات المعدلة يساوي صفرًا")

            used_quantities = {
                int(row["product_id"]): float(row["quantity_per_batch"]) * full_batches
                for row in materials
            }
            normalized_adjustments: list[dict] = []
            modified_mix_cost = 0.0
            for item in adjustments:
                excluded_product_id = int(item["excluded_product_id"])
                batch_count = int(item["batch_count"])
                reason = str(item.get("reason", "")).strip()
                if excluded_product_id not in material_by_id:
                    raise ValueError("الخامة المستبعدة غير موجودة في أمر التصنيع")
                if batch_count <= 0:
                    raise ValueError("عدد الخلطات المعدلة في كل سطر يجب أن يكون أكبر من صفر")
                if not reason:
                    raise ValueError("اكتب سبب استبعاد الخامة")
                supplied = {
                    int(product_id): float(quantity)
                    for product_id, quantity in dict(
                        item.get("actual_material_quantities") or {}
                    ).items()
                }
                group_quantities: dict[int, float] = {}
                group_cost = 0.0
                for material in materials:
                    product_id = int(material["product_id"])
                    if product_id == excluded_product_id:
                        quantity = 0.0
                    elif product_id in supplied:
                        quantity = supplied[product_id]
                    else:
                        quantity = float(material["quantity_per_batch"]) * batch_count
                    if quantity < 0:
                        raise ValueError("كميات الخامات الفعلية لا يمكن أن تكون سالبة")
                    group_quantities[product_id] = quantity
                    used_quantities[product_id] += quantity
                    group_cost += quantity * float(material["unit_cost"] or 0)
                modified_mix_cost += group_cost
                normalized_adjustments.append(
                    {
                        "excluded_product_id": excluded_product_id,
                        "batch_count": batch_count,
                        "reason": reason,
                        "actual_material_quantities": group_quantities,
                        "cost_amount": group_cost,
                    }
                )

            full_mix_cost = sum(
                float(row["quantity_per_batch"])
                * full_batches
                * float(row["unit_cost"] or 0)
                for row in materials
            )
            total_material_cost = full_mix_cost + modified_mix_cost
            used_input_weight = 0.0
            for material in materials:
                product_id = int(material["product_id"])
                issued_quantity = float(material["actual_quantity"] or 0)
                used_quantity = float(used_quantities.get(product_id, 0))
                if used_quantity - issued_quantity > EPSILON:
                    raise ValueError(
                        f"استخدام {material['name']} يتجاوز المصروف. "
                        f"المستخدم {used_quantity:,.3f} والمصروف {issued_quantity:,.3f}"
                    )
                unused_quantity = max(0.0, issued_quantity - used_quantity)
                unit_cost = float(material["unit_cost"] or 0)
                if unused_quantity > EPSILON:
                    connection.execute(
                        """
                        INSERT INTO inventory_moves(
                            product_id, warehouse_id, quantity_in, quantity_out,
                            unit_cost, reference_type, reference_id, notes
                        ) VALUES (?, ?, ?, 0, ?, 'manufacturing_unused_return', ?, ?)
                        """,
                        (
                            product_id,
                            int(order["warehouse_id"]),
                            unused_quantity,
                            unit_cost,
                            int(order_id),
                            f"رد خامات غير مستخدمة عند إتمام {order['order_number']}",
                        ),
                    )
                connection.execute(
                    """
                    UPDATE manufacturing_order_materials
                    SET actual_quantity = ?, total_cost = ?
                    WHERE id = ?
                    """,
                    (used_quantity, used_quantity * unit_cost, int(material["id"])),
                )
                used_input_weight += used_quantity

            output_rows = connection.execute(
                """
                SELECT moo.*, p.code, p.name
                FROM manufacturing_order_outputs moo
                JOIN products p ON p.id = moo.product_id
                WHERE moo.manufacturing_order_id = ?
                ORDER BY moo.id
                """,
                (int(order_id),),
            ).fetchall()
            good_output_quantity = 0.0
            defective_output_quantity = 0.0
            actual_output_weight = 0.0
            normalized_outputs: list[tuple] = []
            for output in output_rows:
                value = outputs.get(int(output["product_id"]), {})
                good_quantity = float(value.get("good_quantity", 0) or 0)
                defective_quantity = float(value.get("defective_quantity", 0) or 0)
                actual_weight = float(value.get("actual_weight_kg", 0) or 0)
                if min(good_quantity, defective_quantity, actual_weight) < 0:
                    raise ValueError("الإنتاج والوزن الفعلي لا يمكن أن تكون قيمًا سالبة")
                if good_quantity > EPSILON and actual_weight <= EPSILON:
                    raise ValueError(f"أدخل الوزن الفعلي للإنتاج السليم للصنف {output['name']}")
                if good_quantity <= EPSILON and actual_weight > EPSILON:
                    raise ValueError(f"أدخل عدد المواسير السليمة للصنف {output['name']}")
                normalized_outputs.append(
                    (output, good_quantity, defective_quantity, actual_weight)
                )
                good_output_quantity += good_quantity
                defective_output_quantity += defective_quantity
                actual_output_weight += actual_weight

            if good_output_quantity <= EPSILON or actual_output_weight <= EPSILON:
                raise ValueError("أدخل الإنتاج السليم ووزنه الفعلي")
            if actual_output_weight + scrap_weight - used_input_weight > EPSILON:
                raise ValueError("وزن الإنتاج والهالك لا يمكن أن يتجاوز وزن الخامات المستخدمة")

            average_input_cost = (
                total_material_cost / used_input_weight
                if used_input_weight > EPSILON
                else 0.0
            )
            scrap_value = scrap_weight * average_input_cost
            finished_cost = max(0.0, total_material_cost - scrap_value)
            cost_per_good_kg = finished_cost / actual_output_weight

            for output, good_quantity, _defective_quantity, actual_weight in normalized_outputs:
                line_cost = actual_weight * cost_per_good_kg
                unit_cost = line_cost / good_quantity if good_quantity > EPSILON else 0.0
                connection.execute(
                    """
                    UPDATE manufacturing_order_outputs
                    SET actual_quantity = ?, unit_cost = ?
                    WHERE id = ?
                    """,
                    (good_quantity, unit_cost, int(output["id"])),
                )
                if good_quantity <= EPSILON:
                    continue
                lot_number = f"{order['order_number']}-FG-{int(output['product_id'])}"
                lot_id = self._ensure_lot(
                    connection,
                    int(output["product_id"]),
                    lot_number,
                    unit_cost,
                )
                cursor = connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing', ?, ?)
                    """,
                    (
                        int(output["product_id"]),
                        int(order["warehouse_id"]),
                        lot_id,
                        good_quantity,
                        unit_cost,
                        int(order_id),
                        f"إنتاج تام {order['order_number']} — وزن فعلي {actual_weight:,.3f} كجم",
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO finished_good_weight_layers(
                        product_id, warehouse_id, source_move_id, lot_id,
                        quantity_in, weight_in_kg, unit_cost_per_kg
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(output["product_id"]),
                        int(order["warehouse_id"]),
                        int(cursor.lastrowid),
                        lot_id,
                        good_quantity,
                        actual_weight,
                        cost_per_good_kg,
                    ),
                )

            scrap_product_id = order["scrap_product_id"]
            if scrap_weight > EPSILON and scrap_product_id is not None:
                scrap_lot = f"{order['order_number']}-SCRAP"
                lot_id = self._ensure_lot(
                    connection,
                    int(scrap_product_id),
                    scrap_lot,
                    average_input_cost,
                )
                connection.execute(
                    """
                    INSERT INTO inventory_moves(
                        product_id, warehouse_id, lot_id, quantity_in, quantity_out,
                        unit_cost, reference_type, reference_id, notes
                    ) VALUES (?, ?, ?, ?, 0, ?, 'manufacturing_scrap', ?, ?)
                    """,
                    (
                        int(scrap_product_id),
                        int(order["warehouse_id"]),
                        lot_id,
                        scrap_weight,
                        average_input_cost,
                        int(order_id),
                        f"هالك مصنع ناتج من {order['order_number']}",
                    ),
                )

            weight_variance = used_input_weight - actual_output_weight - scrap_weight
            connection.execute(
                """
                UPDATE manufacturing_orders
                SET status = 'completed', actual_batches = ?,
                    returned_scrap_quantity = ?, material_cost = ?,
                    finished_cost = ?, weight_variance = ?,
                    notes = CASE
                        WHEN TRIM(COALESCE(notes, '')) = '' THEN ?
                        WHEN TRIM(?) = '' THEN notes
                        ELSE notes || ' | ' || ?
                    END,
                    completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    actual_batches,
                    scrap_weight,
                    total_material_cost,
                    finished_cost,
                    weight_variance,
                    notes.strip(),
                    notes.strip(),
                    notes.strip(),
                    int(order_id),
                ),
            )
            connection.execute(
                "DELETE FROM manufacturing_completion_summaries WHERE manufacturing_order_id = ?",
                (int(order_id),),
            )
            connection.execute(
                """
                INSERT INTO manufacturing_completion_summaries(
                    manufacturing_order_id, planned_batches, actual_batches,
                    full_batches, modified_batches, good_output_quantity,
                    defective_output_quantity, actual_output_weight, scrap_weight,
                    full_mix_cost, modified_mix_cost, total_cost, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(order_id),
                    int(order["planned_batches"]),
                    actual_batches,
                    full_batches,
                    modified_batches,
                    good_output_quantity,
                    defective_output_quantity,
                    actual_output_weight,
                    scrap_weight,
                    full_mix_cost,
                    modified_mix_cost,
                    total_material_cost,
                    notes.strip(),
                ),
            )
            connection.execute(
                "DELETE FROM manufacturing_mix_adjustments WHERE manufacturing_order_id = ?",
                (int(order_id),),
            )
            for adjustment in normalized_adjustments:
                connection.execute(
                    """
                    INSERT INTO manufacturing_mix_adjustments(
                        manufacturing_order_id, excluded_product_id,
                        excluded_batches, reason, actual_materials_json, cost_amount
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(order_id),
                        adjustment["excluded_product_id"],
                        adjustment["batch_count"],
                        adjustment["reason"],
                        json.dumps(
                            adjustment["actual_material_quantities"],
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        adjustment["cost_amount"],
                    ),
                )

            return {
                "planned_batches": int(order["planned_batches"]),
                "actual_batches": actual_batches,
                "full_batches": full_batches,
                "modified_batches": modified_batches,
                "good_output_quantity": good_output_quantity,
                "defective_output_quantity": defective_output_quantity,
                "actual_output_weight": actual_output_weight,
                "scrap_weight": scrap_weight,
                "full_mix_cost": full_mix_cost,
                "modified_mix_cost": modified_mix_cost,
                "total_cost": total_material_cost,
                "finished_cost": finished_cost,
                "weight_variance": weight_variance,
            }

    def get_mix_summary(self, order_id: int) -> dict:
        with self.database.session() as connection:
            ensure_completion_summary_schema(connection)
            summary = connection.execute(
                """
                SELECT s.*, o.order_number, r.name AS recipe_name
                FROM manufacturing_completion_summaries s
                JOIN manufacturing_orders o ON o.id = s.manufacturing_order_id
                JOIN manufacturing_recipes r ON r.id = o.recipe_id
                WHERE s.manufacturing_order_id = ?
                """,
                (int(order_id),),
            ).fetchone()
            if summary is None:
                raise ValueError("لا يوجد تقرير خلطات لهذا الأمر قبل إتمامه")
            adjustments = connection.execute(
                """
                SELECT a.*, p.code, p.name
                FROM manufacturing_mix_adjustments a
                JOIN products p ON p.id = a.excluded_product_id
                WHERE a.manufacturing_order_id = ?
                ORDER BY a.id
                """,
                (int(order_id),),
            ).fetchall()
            material_names = {
                int(row["product_id"]): str(row["name"])
                for row in connection.execute(
                    """
                    SELECT mom.product_id, p.name
                    FROM manufacturing_order_materials mom
                    JOIN products p ON p.id = mom.product_id
                    WHERE mom.manufacturing_order_id = ?
                    """,
                    (int(order_id),),
                ).fetchall()
            }
        result = dict(summary)
        result["adjustments"] = []
        for row in adjustments:
            item = dict(row)
            quantities = {
                int(product_id): float(quantity)
                for product_id, quantity in json.loads(
                    str(item["actual_materials_json"] or "{}")
                ).items()
            }
            item["actual_material_quantities"] = quantities
            item["actual_materials_text"] = "، ".join(
                f"{material_names.get(product_id, product_id)}: {quantity:,.3f}"
                for product_id, quantity in quantities.items()
                if product_id != int(item["excluded_product_id"])
            )
            result["adjustments"].append(item)
        return result


__all__ = ["OrderCompletionManufacturingRepository"]
