EPSILON = 0.0000001


def _remaining_unit_cost(connection, product_id: int) -> float:
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


def estimate_recipe_scrap_cost(database, components: list[dict]) -> dict:
    """Estimate recipe base-material value and scrap cost from current stock layers."""
    normalized = [
        {
            "product_id": int(row["product_id"]),
            "quantity": float(row["quantity_per_batch"]),
        }
        for row in components
        if float(row.get("quantity_per_batch", 0) or 0) > 0
    ]
    total_weight = sum(row["quantity"] for row in normalized)
    if total_weight <= EPSILON:
        return {"total_weight": 0.0, "total_cost": 0.0, "unit_cost": 0.0}

    with database.session() as connection:
        total_cost = sum(
            row["quantity"] * _remaining_unit_cost(connection, row["product_id"])
            for row in normalized
        )
    return {
        "total_weight": total_weight,
        "total_cost": total_cost,
        "unit_cost": total_cost / total_weight,
    }


__all__ = ["estimate_recipe_scrap_cost"]
