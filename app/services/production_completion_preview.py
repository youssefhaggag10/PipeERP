from __future__ import annotations

EPSILON = 0.0000001


def _issued_batch_count(materials: list[dict], actual_batches: int) -> int:
    candidates = []
    for material in materials:
        if str(material.get("component_kind", "material")) == "scrap":
            continue
        per_batch = float(material.get("quantity_per_batch", 0) or 0)
        issued = float(material.get("actual_quantity", 0) or 0)
        if per_batch > EPSILON:
            candidates.append(round(issued / per_batch))
    return max([actual_batches, *candidates])


def calculate_completion_preview(
    *,
    materials: list[dict],
    actual_batches: int,
    outputs: dict[int, dict[str, float]],
    scrap_weight: float,
    adjustments: list[dict],
) -> dict:
    actual_batches = int(actual_batches)
    scrap_weight = float(scrap_weight or 0)
    if actual_batches <= 0:
        raise ValueError("عدد الخلطات الفعلي يجب أن يكون أكبر من صفر")
    if scrap_weight < 0:
        raise ValueError("الهالك لا يمكن أن يكون سالبًا")

    modified_batches = sum(int(item.get("batch_count", 0) or 0) for item in adjustments)
    full_batches = actual_batches - modified_batches
    if full_batches < 0:
        raise ValueError("مجموع الخلطات المعدلة لا يمكن أن يتجاوز عدد الخلطات الفعلي")

    issued_batches = _issued_batch_count(materials, actual_batches)
    material_by_id = {int(row["product_id"]): row for row in materials}
    effective_per_batch = {}
    for product_id, material in material_by_id.items():
        recipe_quantity = float(material["quantity_per_batch"] or 0)
        if str(material.get("component_kind", "material")) == "scrap" and issued_batches > 0:
            issued_per_batch = float(material["actual_quantity"] or 0) / issued_batches
            effective_per_batch[product_id] = min(recipe_quantity, issued_per_batch)
        else:
            effective_per_batch[product_id] = recipe_quantity

    used = {
        product_id: effective_per_batch[product_id] * full_batches
        for product_id in material_by_id
    }
    full_mix_cost = sum(
        used[product_id] * float(material["unit_cost"] or 0)
        for product_id, material in material_by_id.items()
    )

    modified_mix_cost = 0.0
    for adjustment in adjustments:
        excluded_id = int(adjustment["excluded_product_id"])
        batch_count = int(adjustment["batch_count"])
        if excluded_id not in material_by_id:
            raise ValueError("الخامة المستبعدة غير موجودة في أمر التصنيع")
        if batch_count <= 0:
            raise ValueError("عدد الخلطات المعدلة في كل مجموعة يجب أن يكون أكبر من صفر")
        supplied = {
            int(product_id): float(quantity)
            for product_id, quantity in dict(
                adjustment.get("actual_material_quantities") or {}
            ).items()
        }
        if set(supplied).difference(material_by_id):
            raise ValueError("تفاصيل الكميات تحتوي على خامة لا تخص أمر التصنيع")
        for product_id, material in material_by_id.items():
            if product_id == excluded_id:
                quantity = 0.0
            elif product_id in supplied:
                quantity = supplied[product_id]
            else:
                quantity = effective_per_batch[product_id] * batch_count
            if quantity < 0:
                raise ValueError("كميات الخامات الفعلية لا يمكن أن تكون سالبة")
            used[product_id] += quantity
            modified_mix_cost += quantity * float(material["unit_cost"] or 0)

    material_rows = []
    used_input_weight = 0.0
    for product_id, material in material_by_id.items():
        issued = float(material["actual_quantity"] or 0)
        consumed = float(used.get(product_id, 0))
        if consumed - issued > EPSILON:
            raise ValueError(
                f"استخدام {material['name']} يتجاوز المصروف: "
                f"المستخدم {consumed:,.3f} والمصروف {issued:,.3f}"
            )
        unused = max(0.0, issued - consumed)
        material_rows.append(
            {
                "product_id": product_id,
                "code": str(material["code"]),
                "name": str(material["name"]),
                "issued": issued,
                "used": consumed,
                "unused": unused,
            }
        )
        used_input_weight += consumed

    good_output_quantity = 0.0
    defective_output_quantity = 0.0
    actual_output_weight = 0.0
    for output in outputs.values():
        good = float(output.get("good_quantity", 0) or 0)
        defective = float(output.get("defective_quantity", 0) or 0)
        weight = float(output.get("actual_weight_kg", 0) or 0)
        if min(good, defective, weight) < 0:
            raise ValueError("الإنتاج والوزن الفعلي لا يمكن أن تكون قيمًا سالبة")
        if good > EPSILON and weight <= EPSILON:
            raise ValueError("أدخل الوزن الفعلي لكل إنتاج سليم")
        if good <= EPSILON and weight > EPSILON:
            raise ValueError("أدخل عدد الإنتاج السليم المرتبط بالوزن الفعلي")
        good_output_quantity += good
        defective_output_quantity += defective
        actual_output_weight += weight

    if good_output_quantity <= EPSILON or actual_output_weight <= EPSILON:
        raise ValueError("أدخل الإنتاج السليم ووزنه الفعلي")
    if actual_output_weight + scrap_weight - used_input_weight > EPSILON:
        raise ValueError("وزن الإنتاج والهالك لا يمكن أن يتجاوز وزن الخامات المستخدمة")

    return {
        "actual_batches": actual_batches,
        "full_batches": full_batches,
        "modified_batches": modified_batches,
        "good_output_quantity": good_output_quantity,
        "defective_output_quantity": defective_output_quantity,
        "actual_output_weight": actual_output_weight,
        "scrap_weight": scrap_weight,
        "full_mix_cost": full_mix_cost,
        "modified_mix_cost": modified_mix_cost,
        "total_cost": full_mix_cost + modified_mix_cost,
        "materials": material_rows,
    }


__all__ = ["calculate_completion_preview"]
