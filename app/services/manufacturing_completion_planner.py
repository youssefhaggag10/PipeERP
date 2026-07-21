from __future__ import annotations

from sqlite3 import Connection, Row

EPSILON = 0.0000001


def _effective_quantity_per_batch(material: Row, issued_batches: int) -> float:
    recipe_quantity = float(material["quantity_per_batch"] or 0)
    if str(material["component_kind"]) != "scrap" or issued_batches <= 0:
        return recipe_quantity
    issued_per_batch = float(material["actual_quantity"] or 0) / issued_batches
    return min(recipe_quantity, issued_per_batch)


def build_completion_plan(
    connection: Connection,
    order_id: int,
    *,
    actual_batches: int,
    outputs: dict[int, dict[str, float]],
    scrap_weight: float,
    notes: str,
    adjustments: list[dict],
) -> dict:
    actual_batches = int(actual_batches)
    scrap_weight = float(scrap_weight or 0)
    if actual_batches <= 0:
        raise ValueError("عدد الخلطات الفعلي يجب أن يكون أكبر من صفر")
    if scrap_weight < 0:
        raise ValueError("الهالك لا يمكن أن يكون سالبًا")

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

    issued_batches = int(order["actual_batches"] or 0)
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

    modified_batches = sum(int(item.get("batch_count", 0) or 0) for item in adjustments)
    if modified_batches > actual_batches:
        raise ValueError("مجموع الخلطات المعدلة لا يمكن أن يتجاوز عدد الخلطات الفعلي")
    full_batches = actual_batches - modified_batches

    effective_per_batch = {
        int(row["product_id"]): _effective_quantity_per_batch(row, issued_batches)
        for row in materials
    }
    used_quantities = {
        product_id: quantity * full_batches
        for product_id, quantity in effective_per_batch.items()
    }
    full_mix_cost = sum(
        used_quantities[int(row["product_id"])] * float(row["unit_cost"] or 0)
        for row in materials
    )

    normalized_adjustments: list[dict] = []
    modified_mix_cost = 0.0
    for group_number, item in enumerate(adjustments, start=1):
        excluded_product_id = int(item.get("excluded_product_id") or 0)
        batch_count = int(item.get("batch_count", 0) or 0)
        reason = str(item.get("reason", "")).strip()
        if excluded_product_id not in material_by_id:
            raise ValueError(f"الخامة المستبعدة في مجموعة التعديل رقم {group_number} غير صحيحة")
        if batch_count <= 0:
            raise ValueError("عدد الخلطات المعدلة في كل مجموعة يجب أن يكون أكبر من صفر")
        if not reason:
            raise ValueError("اكتب سبب استبعاد الخامة في كل مجموعة تعديل")

        supplied = {
            int(product_id): float(quantity)
            for product_id, quantity in dict(
                item.get("actual_material_quantities") or {}
            ).items()
        }
        if set(supplied).difference(material_by_id):
            raise ValueError("تفاصيل الكميات تحتوي على خامة لا تخص أمر التصنيع")

        group_quantities: dict[int, float] = {}
        group_cost = 0.0
        for material in materials:
            product_id = int(material["product_id"])
            if product_id == excluded_product_id:
                quantity = 0.0
            elif product_id in supplied:
                quantity = supplied[product_id]
            else:
                quantity = effective_per_batch[product_id] * batch_count
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

    material_usage: list[dict] = []
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
        material_usage.append(
            {
                "row": material,
                "product_id": product_id,
                "code": str(material["code"]),
                "name": str(material["name"]),
                "issued_quantity": issued_quantity,
                "used_quantity": used_quantity,
                "unused_quantity": unused_quantity,
                "unit_cost": unit_cost,
                "used_cost": used_quantity * unit_cost,
            }
        )
        used_input_weight += used_quantity

    total_material_cost = full_mix_cost + modified_mix_cost
    calculated_cost = sum(item["used_cost"] for item in material_usage)
    if abs(total_material_cost - calculated_cost) > 0.01:
        total_material_cost = calculated_cost
        modified_mix_cost = max(0.0, total_material_cost - full_mix_cost)

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
    normalized_outputs: list[dict] = []
    good_output_quantity = 0.0
    defective_output_quantity = 0.0
    actual_output_weight = 0.0
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
            {
                "row": output,
                "product_id": int(output["product_id"]),
                "code": str(output["code"]),
                "name": str(output["name"]),
                "good_quantity": good_quantity,
                "defective_quantity": defective_quantity,
                "actual_weight_kg": actual_weight,
            }
        )
        good_output_quantity += good_quantity
        defective_output_quantity += defective_quantity
        actual_output_weight += actual_weight

    if good_output_quantity <= EPSILON or actual_output_weight <= EPSILON:
        raise ValueError("أدخل الإنتاج السليم ووزنه الفعلي")
    if actual_output_weight + scrap_weight - used_input_weight > EPSILON:
        raise ValueError("وزن الإنتاج والهالك لا يمكن أن يتجاوز وزن الخامات المستخدمة")

    average_input_cost = (
        total_material_cost / used_input_weight if used_input_weight > EPSILON else 0.0
    )
    scrap_value = scrap_weight * average_input_cost
    finished_cost = max(0.0, total_material_cost - scrap_value)
    cost_per_good_kg = finished_cost / actual_output_weight
    weight_variance = used_input_weight - actual_output_weight - scrap_weight

    return {
        "order": order,
        "planned_batches": int(order["planned_batches"] or 0),
        "issued_batches": issued_batches,
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
        "cost_per_good_kg": cost_per_good_kg,
        "average_input_cost": average_input_cost,
        "used_input_weight": used_input_weight,
        "weight_variance": weight_variance,
        "notes": str(notes or "").strip(),
        "materials": material_usage,
        "outputs": normalized_outputs,
        "adjustments": normalized_adjustments,
    }


def public_completion_plan(plan: dict) -> dict:
    result = {
        key: plan[key]
        for key in (
            "planned_batches",
            "issued_batches",
            "actual_batches",
            "full_batches",
            "modified_batches",
            "good_output_quantity",
            "defective_output_quantity",
            "actual_output_weight",
            "scrap_weight",
            "full_mix_cost",
            "modified_mix_cost",
            "total_cost",
            "finished_cost",
            "used_input_weight",
            "weight_variance",
            "notes",
        )
    }
    result["materials"] = [
        {key: item[key] for key in item if key != "row"} for item in plan["materials"]
    ]
    result["returns"] = [
        {key: item[key] for key in item if key != "row"}
        for item in plan["materials"]
        if float(item["unused_quantity"]) > EPSILON
    ]
    result["outputs"] = [
        {key: item[key] for key in item if key != "row"} for item in plan["outputs"]
    ]
    result["adjustments"] = [dict(item) for item in plan["adjustments"]]
    return result


__all__ = ["EPSILON", "build_completion_plan", "public_completion_plan"]
