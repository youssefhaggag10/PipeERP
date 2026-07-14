from datetime import datetime
from uuid import uuid4

from app.repositories.inventory_repository import InventoryRepository


class AutomatedInventoryRepository(InventoryRepository):
    """Inventory repository that removes manual lot-number dependency."""

    def post_adjustment(
        self,
        product_id: int,
        quantity: float,
        notes: str = "",
        *,
        unit_cost: float = 0,
        lot_number: str = "",
    ) -> None:
        generated_lot = lot_number.strip()
        if quantity > 0 and not generated_lot:
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            generated_lot = f"ADJ-{product_id}-{stamp}-{uuid4().hex[:6].upper()}"
        super().post_adjustment(
            product_id,
            quantity,
            notes,
            unit_cost=unit_cost,
            lot_number=generated_lot,
        )


__all__ = ["AutomatedInventoryRepository"]
