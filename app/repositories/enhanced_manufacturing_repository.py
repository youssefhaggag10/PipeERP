from app.repositories.manufacturing_repository import ManufacturingRepository


class EnhancedManufacturingRepository(ManufacturingRepository):
    """Manufacturing actions that preserve inventory and audit integrity."""

    def update_recipe(
        self,
        recipe_id: int,
        *,
        code: str,
        name: str,
        output_product_ids: list[int],
        components: list[dict],
        suggested_scrap_per_batch: float = 0,
        notes: