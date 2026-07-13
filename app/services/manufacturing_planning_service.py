from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class ProductionTarget:
    product_id: int
    quantity: float
    standard_weight_kg: float

    @property
    def target_weight(self) -> float:
        return self.quantity * self.standard_weight_kg


@dataclass(frozen=True)
class BatchPlan:
    target_weight: float
    base_batch_weight: float
    scrap_per_batch: float
    batch_weight: float
    batches: int
    planned_input_weight: float
    expected_overage_weight: float


def calculate_batch_plan(
    targets: list[ProductionTarget],
    material_quantities_per_batch: list[float],
    scrap_quantities_per_batch: list[float] | None = None,
) -> BatchPlan:
    """Plan shared batches for several sizes that use the same recipe family."""
    if not targets:
        raise ValueError("أضف منتجًا نهائيًا واحدًا على الأقل")
    for target in targets:
        if target.quantity <= 0 or target.standard_weight_kg <= 0:
            raise ValueError("الكمية والوزن القياسي يجب أن يكونا أكبر من صفر")

    materials = [float(value) for value in material_quantities_per_batch]
    scraps = [float(value) for value in (scrap_quantities_per_batch or [])]
    if not materials or any(value <= 0 for value in materials):
        raise ValueError("الخلطة تحتاج خامة أساسية واحدة على الأقل بكمية صحيحة")
    if any(value < 0 for value in scraps):
        raise ValueError("كمية الكسر لا يمكن أن تكون سالبة")

    target_weight = sum(target.target_weight for target in targets)
    base_batch_weight = sum(materials)
    scrap_per_batch = sum(scraps)
    batch_weight = base_batch_weight + scrap_per_batch
    batches = int(ceil(target_weight / batch_weight))
    planned_input = batches * batch_weight
    return BatchPlan(
        target_weight=target_weight,
        base_batch_weight=base_batch_weight,
        scrap_per_batch=scrap_per_batch,
        batch_weight=batch_weight,
        batches=batches,
        planned_input_weight=planned_input,
        expected_overage_weight=planned_input - target_weight,
    )
