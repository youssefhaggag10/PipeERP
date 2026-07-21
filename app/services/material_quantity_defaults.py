from __future__ import annotations


def default_actual_material_quantities(
    materials: list[dict],
    *,
    excluded_product_id: int,
    batch_count: int,
    issued_batches: int,
) -> dict[int, float]:
    """Build safe group defaults from quantities that were actually issued."""
    batch_count = int(batch_count)
    issued_batches = max(1, int(issued_batches))
    if batch_count <= 0:
        return {}

    defaults: dict[int, float] = {}
    for material in materials:
        product_id = int(material["product_id"])
        if product_id == int(excluded_product_id):
            continue

        quantity_per_batch = float(material.get("quantity_per_batch", 0) or 0)
        if str(material.get("component_kind", "material")) == "scrap":
            issued_quantity = float(material.get("actual_quantity", 0) or 0)
            quantity_per_batch = min(
                quantity_per_batch,
                issued_quantity / issued_batches,
            )
        defaults[product_id] = quantity_per_batch * batch_count
    return defaults


__all__ = ["default_actual_material_quantities"]
