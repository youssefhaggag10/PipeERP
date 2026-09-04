from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from app.domain.common.decimal import as_decimal, quantity


@dataclass(frozen=True, slots=True)
class ProductionTarget:
    product_id: int
    pieces: Decimal
    standard_weight_kg: Decimal

    @property
    def target_weight_kg(self) -> Decimal:
        return self.pieces * self.standard_weight_kg


@dataclass(frozen=True, slots=True)
class BatchPlan:
    target_weight_kg: Decimal
    base_material_kg_per_batch: Decimal
    reused_scrap_kg_per_batch: Decimal
    batches: int
    planned_input_weight_kg: Decimal
    expected_overage_kg: Decimal


@dataclass(frozen=True, slots=True)
class StockAwarePlan:
    changed: bool
    old_batches: int
    new_batches: int
    target_weight_kg: Decimal
    planned_scrap_kg: Decimal
    usable_scrap_kg: Decimal
    planned_input_weight_kg: Decimal
    expected_overage_kg: Decimal


def calculate_batch_plan(
    *,
    targets: list[ProductionTarget],
    material_quantities_kg: list[Decimal],
    reused_scrap_quantities_kg: list[Decimal] | None = None,
) -> BatchPlan:
    if not targets:
        raise ValueError("أضف منتجًا نهائيًا واحدًا على الأقل")
    if any(target.pieces <= 0 or target.standard_weight_kg <= 0 for target in targets):
        raise ValueError("الكمية والوزن القياسي يجب أن يكونا أكبر من صفر")
    if not material_quantities_kg or any(item <= 0 for item in material_quantities_kg):
        raise ValueError("الخلطة تحتاج خامة أساسية واحدة على الأقل")

    scraps = reused_scrap_quantities_kg or []
    if any(item < 0 for item in scraps):
        raise ValueError("كمية الكسر لا يمكن أن تكون سالبة")

    target_weight = sum((target.target_weight_kg for target in targets), Decimal("0"))
    base_weight = sum(material_quantities_kg, Decimal("0"))
    scrap_weight = sum(scraps, Decimal("0"))
    batch_weight = base_weight + scrap_weight
    batches = int((target_weight / batch_weight).to_integral_value(rounding=ROUND_CEILING))
    planned_input = batch_weight * batches

    return BatchPlan(
        target_weight_kg=quantity(target_weight),
        base_material_kg_per_batch=quantity(base_weight),
        reused_scrap_kg_per_batch=quantity(scrap_weight),
        batches=batches,
        planned_input_weight_kg=quantity(planned_input),
        expected_overage_kg=quantity(planned_input - target_weight),
    )


def target(product_id: int, pieces: object, standard_weight_kg: object) -> ProductionTarget:
    return ProductionTarget(
        product_id=product_id,
        pieces=as_decimal(pieces, field="الكمية"),
        standard_weight_kg=as_decimal(standard_weight_kg, field="الوزن القياسي"),
    )


def replan_for_available_scrap(
    *,
    target_weight_kg: Decimal,
    base_material_kg_per_batch: Decimal,
    scrap_quantities_kg_per_batch: list[Decimal],
    available_scrap_quantities_kg: list[Decimal],
    old_batches: int,
) -> StockAwarePlan:
    if target_weight_kg <= 0 or base_material_kg_per_batch <= 0:
        raise ValueError("تعذر حساب وزن أمر التصنيع أو وزن الخلطة الأساسية")
    if old_batches <= 0:
        raise ValueError("عدد الخلطات المخطط يجب أن يكون أكبر من صفر")
    if len(scrap_quantities_kg_per_batch) != len(available_scrap_quantities_kg):
        raise ValueError("مصادر الكسر المتاحة لا تطابق خطة أمر التصنيع")
    if any(item <= 0 for item in scrap_quantities_kg_per_batch):
        raise ValueError("كمية الكسر في الخلطة يجب أن تكون أكبر من صفر")
    if any(item < 0 for item in available_scrap_quantities_kg):
        raise ValueError("رصيد الكسر لا يمكن أن يكون سالبًا")

    batches = old_batches
    while True:
        planned_scrap = sum(
            (item * Decimal(batches) for item in scrap_quantities_kg_per_batch),
            Decimal("0"),
        )
        usable_scrap = sum(
            (
                min(per_batch * Decimal(batches), available)
                for per_batch, available in zip(
                    scrap_quantities_kg_per_batch,
                    available_scrap_quantities_kg,
                    strict=True,
                )
            ),
            Decimal("0"),
        )
        input_weight = base_material_kg_per_batch * Decimal(batches) + usable_scrap
        if input_weight >= target_weight_kg:
            break
        batches += 1
        if batches > 1_000_000:
            raise ValueError("تعذر حساب عدد خلطات صالح لأمر التصنيع")

    return StockAwarePlan(
        changed=batches != old_batches,
        old_batches=old_batches,
        new_batches=batches,
        target_weight_kg=quantity(target_weight_kg),
        planned_scrap_kg=quantity(planned_scrap),
        usable_scrap_kg=quantity(usable_scrap),
        planned_input_weight_kg=quantity(input_weight),
        expected_overage_kg=quantity(input_weight - target_weight_kg),
    )
