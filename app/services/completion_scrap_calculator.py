from __future__ import annotations

EPSILON = 0.0000001


def _effective_quantity_per_batch(material: dict, issued_batches: int) -> float:
    recipe_quantity = float(material.get("quantity_per_batch", 0) or 0)
    if str(material.get("component_kind", "material")) != "scrap" or issued_batches <= 0:
        return recipe_quantity
    issued_per_batch = float(material.get("actual_quantity", 0) or 0) / issued_batches
    return min(recipe_quantity, issued_per_batch)


def calculate_completion_input_weight(
    *,
    materials: list[dict],
    actual_batches: int,
    issued_batches: int,
    adjustments: list[dict] | None = None,
) -> float:
    """Return the material weight consumed by full and modified batch groups."""

    actual_batches = int(actual_batches)
    issued_batches = int(issued_batches)
    adjustments = list(adjustments or [])
    if actual_batches <= 0:
        raise ValueError("عدد الخلطات الفعلي يجب أن يكون أكبر من صفر")
    if issued_batches <= 0:
        raise ValueError("عدد الخلطات المصروفة يجب أن يكون أكبر من صفر")
    material_by_id = {int(row["product_id"]): row for row in materials}
    effective_per_batch = {
        product_id: _effective_quantity_per_batch(material, issued_batches)
        for product_id, material in material_by_id.items()
    }
    modified_batches = sum(int(item.get("batch_count", 0) or 0) for item in adjustments)
    full_batches = actual_batches - modified_batches
    if full_batches < 0:
        raise ValueError("مجموع الخلطات المعدلة لا يمكن أن يتجاوز عدد الخلطات الفعلي")

    used = {
        product_id: quantity_per_batch * full_batches
        for product_id, quantity_per_batch in effective_per_batch.items()
    }
    for adjustment in adjustments:
        excluded_product_id = int(adjustment.get("excluded_product_id") or 0)
        batch_count = int(adjustment.get("batch_count", 0) or 0)
        if excluded_product_id not in material_by_id or batch_count <= 0:
            continue
        supplied = {
            int(product_id): float(quantity)
            for product_id, quantity in dict(
                adjustment.get("actual_material_quantities") or {}
            ).items()
        }
        for product_id in material_by_id:
            if product_id == excluded_product_id:
                quantity = 0.0
            elif product_id in supplied:
                quantity = supplied[product_id]
            else:
                quantity = effective_per_batch[product_id] * batch_count
            if quantity < 0:
                raise ValueError("كميات الخامات الفعلية لا يمكن أن تكون سالبة")
            used[product_id] += quantity

    total = 0.0
    for product_id, material in material_by_id.items():
        consumed = float(used.get(product_id, 0) or 0)
        issued = float(material.get("actual_quantity", 0) or 0)
        if actual_batches > issued_batches:
            issued += effective_per_batch[product_id] * (actual_batches - issued_batches)
        if consumed - issued > EPSILON:
            raise ValueError(
                f"استخدام {material.get('name', product_id)} يتجاوز المصروف"
            )
        total += consumed
    return total


def calculate_suggested_scrap_weight(
    *,
    materials: list[dict],
    actual_batches: int,
    issued_batches: int,
    output_weights: dict[int, float],
    adjustments: list[dict] | None = None,
) -> float:
    input_weight = calculate_completion_input_weight(
        materials=materials,
        actual_batches=actual_batches,
        issued_batches=issued_batches,
        adjustments=adjustments,
    )
    good_weight = 0.0
    for weight in output_weights.values():
        value = float(weight or 0)
        if value < 0:
            raise ValueError("وزن الإنتاج السليم لا يمكن أن يكون سالبًا")
        good_weight += value
    return max(0.0, input_weight - good_weight)


__all__ = [
    "calculate_completion_input_weight",
    "calculate_suggested_scrap_weight",
]
