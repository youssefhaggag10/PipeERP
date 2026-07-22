from __future__ import annotations

import json

from app.database.completion_summary_schema import ensure_completion_summary_schema
from app.repositories.order_completion_manufacturing_repository import (
    OrderCompletionManufacturingRepository,
)
from app.services.manufacturing_completion_planner import (
    EPSILON,
    build_completion_plan,
    public_completion_plan,
)


class WizardManufacturingRepository(OrderCompletionManufacturingRepository):
    """Aggregate completion with automatic full/modified mix counts."""

    def preview_order_completion(
        self,
        order_id: int,
        *,
        actual_batches: int,
        outputs: dict[int, dict[str, float]],
        scrap_weight: float = 0,
        notes: str = "",
        adjustments: list[dict] | None = None,
    ) -> dict:
        with self.database.session() as connection:
            ensure_completion_summary_schema(connection)
            plan = build_completion_plan(
                connection,
                int(order_id),
                actual_batches=actual_batches,
                outputs=outputs,
                scrap_weight=scrap_weight,
                notes=notes,
                adjustments=list(adjustments or []),
            )
        return public_completion_plan(plan)

    def complete_order_with_mix_summary(
        self,
        order_id: int,
        *,
        actual_batches: int,
        outputs: dict[int, dict[str, float]],
        scrap_weight: float = 0,
        notes: str = "",
        adjustments: list[dict] | None = None,
        full_batches: int | None = None,
        modified_batches: int | None = None,
    ) -> dict:
        with self.database.session(immediate=True) as connection:
            ensure_completion_summary_schema(connection)
            self._issue_additional_batches(
                connection,
                int(order_id),
                target_batches=int(actual_batches),
            )
            plan = build_completion_plan(
                connection,
                int(order_id),
                actual_batches=actual_batches,
                outputs=outputs,
                scrap_weight=scrap_weight,
                notes=notes,
                adjustments=list(adjustments or []),
            )
            if full_batches is not None and int(full_batches) != int(plan["full_batches"]):
                raise ValueError("عدد الخلطات الكاملة لا يطابق مجموعات التعديل")
            if modified_batches is not None and int(modified_batches) != int(
                plan["modified_batches"]
            ):
                raise ValueError("عدد الخلطات المعدلة لا يطابق مجموعات التعديل")
            order = plan["order"]

            for material in plan["materials"]:
                if float(material["unused_quantity"]) > EPSILON:
                    connection.execute(
                        """
                        INSERT INTO inventory_moves(
                            product_id, warehouse_id, quantity_in, quantity_out,
                            unit_cost, reference_type, reference_id, notes
                        ) VALUES (?, ?, ?, 0, ?, 'manufacturing_unused_return', ?, ?)
                        """,
                        (
                            material["product_id"],
                            int(order["warehouse_id"]),
                            material["unused_quantity"],
                            material["unit_cost"],
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
                    (
                        material["used_quantity"],
                        material["used_cost"],
                        int(material["row"]["id"]),
                    ),
                )

            connection.execute(
                "DELETE FROM manufacturing_completion_outputs WHERE manufacturing_order_id = ?",
                (int(order_id),),
            )
            for output in plan["outputs"]:
                good_quantity = float(output["good_quantity"])
                actual_weight = float(output["actual_weight_kg"])
                line_cost = actual_weight * float(plan["cost_per_good_kg"])
                unit_cost = line_cost / good_quantity if good_quantity > EPSILON else 0.0
                connection.execute(
                    """
                    UPDATE manufacturing_order_outputs
                    SET actual_quantity = ?, unit_cost = ?
                    WHERE id = ?
                    """,
                    (good_quantity, unit_cost, int(output["row"]["id"])),
                )
                connection.execute(
                    """
                    INSERT INTO manufacturing_completion_outputs(
                        manufacturing_order_id, product_id, good_quantity,
                        defective_quantity, actual_weight_kg, unit_cost
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(order_id),
                        output["product_id"],
                        good_quantity,
                        output["defective_quantity"],
                        actual_weight,
                        unit_cost,
                    ),
                )
                if good_quantity <= EPSILON:
                    continue
                lot_number = f"{order['order_number']}-FG-{output['product_id']}"
                lot_id = self._ensure_lot(
                    connection,
                    output["product_id"],
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
                        output["product_id"],
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
                        output["product_id"],
                        int(order["warehouse_id"]),
                        int(cursor.lastrowid),
                        lot_id,
                        good_quantity,
                        actual_weight,
                        float(plan["cost_per_good_kg"]),
                    ),
                )

            scrap_product_id = order["scrap_product_id"]
            if float(plan["scrap_weight"]) > EPSILON and scrap_product_id is not None:
                scrap_lot = f"{order['order_number']}-SCRAP"
                lot_id = self._ensure_lot(
                    connection,
                    int(scrap_product_id),
                    scrap_lot,
                    float(plan["average_input_cost"]),
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
                        float(plan["scrap_weight"]),
                        float(plan["average_input_cost"]),
                        int(order_id),
                        f"هالك مصنع ناتج من {order['order_number']}",
                    ),
                )

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
                    plan["actual_batches"],
                    plan["scrap_weight"],
                    plan["total_cost"],
                    plan["finished_cost"],
                    plan["weight_variance"],
                    plan["notes"],
                    plan["notes"],
                    plan["notes"],
                    int(order_id),
                ),
            )
            self._store_completion_summary(connection, int(order_id), plan)

        return public_completion_plan(plan)

    def _issue_additional_batches(
        self,
        connection,
        order_id: int,
        *,
        target_batches: int,
    ) -> None:
        order = connection.execute(
            "SELECT * FROM manufacturing_orders WHERE id = ?",
            (int(order_id),),
        ).fetchone()
        if order is None or str(order["status"]) != "in_progress":
            raise ValueError("يمكن إتمام أمر تصنيع جارٍ فقط")

        issued_batches = int(order["actual_batches"] or 0)
        additional_batches = int(target_batches) - issued_batches
        if additional_batches <= 0:
            return

        materials = connection.execute(
            """
            SELECT * FROM manufacturing_order_materials
            WHERE manufacturing_order_id = ?
            ORDER BY id
            """,
            (int(order_id),),
        ).fetchall()
        for material in materials:
            quantity = float(material["quantity_per_batch"] or 0) * additional_batches
            if str(material["component_kind"]) == "scrap":
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
                order_id=int(order_id),
                warehouse_id=int(order["warehouse_id"]),
                material_id=int(material["id"]),
                product_id=int(material["product_id"]),
                quantity=quantity,
            )

        connection.execute(
            "UPDATE manufacturing_orders SET actual_batches = ? WHERE id = ?",
            (int(target_batches), int(order_id)),
        )
        self._refresh_material_cost(connection, int(order_id))

    @staticmethod
    def _store_completion_summary(connection, order_id: int, plan: dict) -> None:
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
                plan["planned_batches"],
                plan["actual_batches"],
                plan["full_batches"],
                plan["modified_batches"],
                plan["good_output_quantity"],
                plan["defective_output_quantity"],
                plan["actual_output_weight"],
                plan["scrap_weight"],
                plan["full_mix_cost"],
                plan["modified_mix_cost"],
                plan["total_cost"],
                plan["notes"],
            ),
        )
        connection.execute(
            "DELETE FROM manufacturing_mix_adjustments WHERE manufacturing_order_id = ?",
            (int(order_id),),
        )
        for adjustment in plan["adjustments"]:
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
            completion_outputs = connection.execute(
                """
                SELECT co.*, p.code, p.name
                FROM manufacturing_completion_outputs co
                JOIN products p ON p.id = co.product_id
                WHERE co.manufacturing_order_id = ?
                ORDER BY co.id
                """,
                (int(order_id),),
            ).fetchall()
            materials = connection.execute(
                """
                SELECT mom.product_id, p.code, p.name,
                       mom.actual_quantity AS used_quantity,
                       mom.unit_cost, mom.total_cost AS used_cost,
                       COALESCE((
                           SELECT SUM(im.quantity_in)
                           FROM inventory_moves im
                           WHERE im.reference_type = 'manufacturing_unused_return'
                             AND im.reference_id = mom.manufacturing_order_id
                             AND im.product_id = mom.product_id
                       ), 0) AS unused_quantity
                FROM manufacturing_order_materials mom
                JOIN products p ON p.id = mom.product_id
                WHERE mom.manufacturing_order_id = ?
                ORDER BY mom.id
                """,
                (int(order_id),),
            ).fetchall()
            material_names = {int(row["product_id"]): str(row["name"]) for row in materials}

        result = dict(summary)
        result["outputs"] = [dict(row) for row in completion_outputs]
        result["materials"] = []
        result["returns"] = []
        for row in materials:
            item = dict(row)
            item["issued_quantity"] = float(item["used_quantity"] or 0) + float(
                item["unused_quantity"] or 0
            )
            result["materials"].append(item)
            if float(item["unused_quantity"] or 0) > EPSILON:
                result["returns"].append(item)

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


__all__ = ["WizardManufacturingRepository"]
