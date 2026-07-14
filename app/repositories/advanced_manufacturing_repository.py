from app.repositories.enhanced_manufacturing_repository import EnhancedManufacturingRepository
from app.services.manufacturing_planning_service import ProductionTarget, calculate_batch_plan


class AdvancedManufacturingRepository(EnhancedManufacturingRepository):
    """Manufacturing workflow helpers for safer, lower-error operation."""

    def material_availability(
        self,
        order_id: int,
        *,
        target_batches: int | None = None,
        additional_only: bool = False,
    ) -> list[dict]:
        order = self.get_order(order_id)
        batches = int(target_batches if target_batches is not None else order["planned_batches"])
        if batches < 0:
            raise ValueError("عدد الخلطات لا يمكن أن يكون سالبًا")
        current_batches = int(order["actual_batches