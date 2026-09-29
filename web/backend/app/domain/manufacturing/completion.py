from dataclasses import dataclass
from decimal import Decimal

from app.domain.common.decimal import money, quantity


@dataclass(frozen=True, slots=True)
class CompletionMaterial:
    product_id: str
    name: str
    component_kind: str
    quantity_per_batch: Decimal
    issued_quantity: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class MixAdjustment:
    excluded_product_id: str
    batch_count: int
    reason: str
    actual_material_quantities: dict[str, Decimal]


@dataclass(frozen=True, slots=True)
class CompletionOutput:
    product_id: str
    name: str
    good_quantity: Decimal
    defective_quantity: Decimal
    actual_weight_kg: Decimal


@dataclass(frozen=True, slots=True)
class MaterialUsage:
    product_id: str
    issued_quantity: Decimal
    used_quantity: Decimal
    unused_quantity: Decimal
    unit_cost: Decimal
    used_cost: Decimal


@dataclass(frozen=True, slots=True)
class OutputCost:
    product_id: str
    good_quantity: Decimal
    defective_quantity: Decimal
    actual_weight_kg: Decimal
    line_cost: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class AdjustmentCost:
    excluded_product_id: str
    batch_count: int
    reason: str
    actual_material_quantities: dict[str, Decimal]
    cost_amount: Decimal


@dataclass(frozen=True, slots=True)
class CompletionPlan:
    actual_batches: int
    full_batches: int
    modified_batches: int
    good_output_quantity: Decimal
    defective_output_quantity: Decimal
    actual_output_weight_kg: Decimal
    scrap_weight_kg: Decimal
    used_input_weight_kg: Decimal
    full_mix_cost: Decimal
    modified_mix_cost: Decimal
    total_material_cost: Decimal
    average_input_cost_per_kg: Decimal
    scrap_value: Decimal
    finished_cost: Decimal
    cost_per_good_kg: Decimal
    weight_variance_kg: Decimal
    materials: tuple[MaterialUsage, ...]
    outputs: tuple[OutputCost, ...]
    adjustments: tuple[AdjustmentCost, ...]


def _validate_completion_counts(
    *,
    actual_batches: int,
    issued_batches: int,
    scrap_weight_kg: Decimal,
    materials: list[CompletionMaterial],
    adjustments: list[MixAdjustment],
) -> tuple[dict[str, CompletionMaterial], int, int]:
    if actual_batches <= 0:
        raise ValueError("عدد الخلطات الفعلي يجب أن يكون أكبر من صفر")
    if issued_batches <= 0:
        raise ValueError("عدد الخلطات المصروفة يجب أن يكون أكبر من صفر")
    if scrap_weight_kg < 0:
        raise ValueError("الهالك لا يمكن أن يكون سالبًا")
    if not materials:
        raise ValueError("أمر التصنيع لا يحتوي على خامات مصروفة")
    material_by_id = {item.product_id: item for item in materials}
    if len(material_by_id) != len(materials):
        raise ValueError("لا يمكن تكرار الخامة في أمر التصنيع")
    modified_batches = sum(item.batch_count for item in adjustments)
    if modified_batches > actual_batches:
        raise ValueError("مجموع الخلطات المعدلة لا يمكن أن يتجاوز عدد الخلطات الفعلي")
    return material_by_id, modified_batches, actual_batches - modified_batches


def _effective_per_batch(
    materials: list[CompletionMaterial], issued_batches: int
) -> dict[str, Decimal]:
    result: dict[str, Decimal] = {}
    for item in materials:
        if item.quantity_per_batch <= 0 or item.issued_quantity < 0 or item.unit_cost < 0:
            raise ValueError("بيانات الخامات المصروفة غير صحيحة")
        per_batch = item.quantity_per_batch
        if item.component_kind == "scrap":
            per_batch = min(per_batch, item.issued_quantity / Decimal(issued_batches))
        elif item.component_kind != "material":
            raise ValueError("نوع خامة أمر التصنيع غير صحيح")
        result[item.product_id] = per_batch
    return result


def _adjustment_quantities(
    adjustment: MixAdjustment,
    *,
    material_by_id: dict[str, CompletionMaterial],
    effective_per_batch: dict[str, Decimal],
) -> tuple[dict[str, Decimal], Decimal]:
    quantities: dict[str, Decimal] = {}
    cost = Decimal("0")
    for product_id, material in material_by_id.items():
        if product_id == adjustment.excluded_product_id:
            used_quantity = Decimal("0")
        else:
            used_quantity = adjustment.actual_material_quantities.get(
                product_id,
                effective_per_batch[product_id] * Decimal(adjustment.batch_count),
            )
        if used_quantity < 0:
            raise ValueError("كميات الخامات الفعلية لا يمكن أن تكون سالبة")
        quantities[product_id] = used_quantity
        cost += used_quantity * material.unit_cost
    return quantities, money(cost)


def _apply_adjustments(
    adjustments: list[MixAdjustment],
    *,
    material_by_id: dict[str, CompletionMaterial],
    effective_per_batch: dict[str, Decimal],
    used: dict[str, Decimal],
) -> tuple[list[AdjustmentCost], Decimal]:
    normalized: list[AdjustmentCost] = []
    total_cost = Decimal("0")
    for index, adjustment in enumerate(adjustments, start=1):
        if adjustment.excluded_product_id not in material_by_id:
            raise ValueError(f"الخامة المستبعدة في مجموعة التعديل رقم {index} غير صحيحة")
        if adjustment.batch_count <= 0:
            raise ValueError("عدد الخلطات المعدلة في كل مجموعة يجب أن يكون أكبر من صفر")
        reason = adjustment.reason.strip()
        if not reason:
            raise ValueError("اكتب سبب استبعاد الخامة في كل مجموعة تعديل")
        if set(adjustment.actual_material_quantities).difference(material_by_id):
            raise ValueError("تفاصيل الكميات تحتوي على خامة لا تخص أمر التصنيع")
        group_quantities, group_cost = _adjustment_quantities(
            adjustment,
            material_by_id=material_by_id,
            effective_per_batch=effective_per_batch,
        )
        for product_id, used_quantity in group_quantities.items():
            used[product_id] += used_quantity
        total_cost += group_cost
        normalized.append(
            AdjustmentCost(
                excluded_product_id=adjustment.excluded_product_id,
                batch_count=adjustment.batch_count,
                reason=reason,
                actual_material_quantities={
                    product_id: quantity(used_quantity)
                    for product_id, used_quantity in group_quantities.items()
                },
                cost_amount=group_cost,
            )
        )
    return normalized, money(total_cost)


def _material_usage(
    materials: list[CompletionMaterial], used: dict[str, Decimal]
) -> tuple[list[MaterialUsage], Decimal, Decimal]:
    result: list[MaterialUsage] = []
    used_input_weight = Decimal("0")
    for item in materials:
        used_quantity = quantity(used[item.product_id])
        if used_quantity > item.issued_quantity:
            raise ValueError(
                f"استخدام {item.name} يتجاوز المصروف. "
                f"المستخدم {used_quantity} والمصروف {item.issued_quantity}"
            )
        result.append(
            MaterialUsage(
                product_id=item.product_id,
                issued_quantity=quantity(item.issued_quantity),
                used_quantity=used_quantity,
                unused_quantity=quantity(item.issued_quantity - used_quantity),
                unit_cost=quantity(item.unit_cost),
                used_cost=money(used_quantity * item.unit_cost),
            )
        )
        used_input_weight += used_quantity
    total_cost = money(sum((item.used_cost for item in result), Decimal("0")))
    return result, used_input_weight, total_cost


def _validate_output(output: CompletionOutput) -> None:
    if min(output.good_quantity, output.defective_quantity, output.actual_weight_kg) < 0:
        raise ValueError("الإنتاج والوزن الفعلي لا يمكن أن تكون قيمًا سالبة")
    if output.good_quantity > 0 and output.actual_weight_kg <= 0:
        raise ValueError(f"أدخل الوزن الفعلي للإنتاج السليم للصنف {output.name}")
    if output.good_quantity <= 0 and output.actual_weight_kg > 0:
        raise ValueError(f"أدخل عدد المواسير السليمة للصنف {output.name}")


def _output_totals(outputs: list[CompletionOutput]) -> tuple[Decimal, Decimal, Decimal]:
    for output in outputs:
        _validate_output(output)
    return (
        sum((item.good_quantity for item in outputs), Decimal("0")),
        sum((item.defective_quantity for item in outputs), Decimal("0")),
        sum((item.actual_weight_kg for item in outputs), Decimal("0")),
    )


def _allocate_output_costs(
    outputs: list[CompletionOutput], *, finished_cost: Decimal, cost_per_good_kg: Decimal
) -> list[OutputCost]:
    nonzero_outputs = [item for item in outputs if item.good_quantity > 0]
    result: list[OutputCost] = []
    allocated_cost = Decimal("0")
    for index, output in enumerate(nonzero_outputs):
        is_last = index == len(nonzero_outputs) - 1
        line_cost = money(
            finished_cost - allocated_cost
            if is_last
            else output.actual_weight_kg * cost_per_good_kg
        )
        allocated_cost += line_cost
        result.append(
            OutputCost(
                product_id=output.product_id,
                good_quantity=quantity(output.good_quantity),
                defective_quantity=quantity(output.defective_quantity),
                actual_weight_kg=quantity(output.actual_weight_kg),
                line_cost=line_cost,
                unit_cost=quantity(line_cost / output.good_quantity),
            )
        )
    output_cost_by_id = {item.product_id for item in result}
    result.extend(
        OutputCost(
            product_id=output.product_id,
            good_quantity=Decimal("0"),
            defective_quantity=quantity(output.defective_quantity),
            actual_weight_kg=Decimal("0"),
            line_cost=Decimal("0"),
            unit_cost=Decimal("0"),
        )
        for output in outputs
        if output.product_id not in output_cost_by_id
    )
    return result


def calculate_completion_plan(
    *,
    actual_batches: int,
    issued_batches: int,
    materials: list[CompletionMaterial],
    outputs: list[CompletionOutput],
    scrap_weight_kg: Decimal = Decimal("0"),
    adjustments: list[MixAdjustment] | None = None,
) -> CompletionPlan:
    """Apply the active desktop completion rules using fixed-precision decimals."""
    adjustments = adjustments or []
    material_by_id, modified_batches, full_batches = _validate_completion_counts(
        actual_batches=actual_batches,
        issued_batches=issued_batches,
        scrap_weight_kg=scrap_weight_kg,
        materials=materials,
        adjustments=adjustments,
    )
    effective_per_batch = _effective_per_batch(materials, issued_batches)
    used = {
        product_id: per_batch * Decimal(full_batches)
        for product_id, per_batch in effective_per_batch.items()
    }
    full_mix_cost = money(
        sum((used[item.product_id] * item.unit_cost for item in materials), Decimal("0"))
    )
    normalized_adjustments, modified_mix_cost = _apply_adjustments(
        adjustments,
        material_by_id=material_by_id,
        effective_per_batch=effective_per_batch,
        used=used,
    )
    material_usage, used_input_weight, total_material_cost = _material_usage(materials, used)
    if total_material_cost != money(full_mix_cost + modified_mix_cost):
        modified_mix_cost = money(max(Decimal("0"), total_material_cost - full_mix_cost))
    good_quantity, defective_quantity, actual_output_weight = _output_totals(outputs)
    if good_quantity <= 0 or actual_output_weight <= 0:
        raise ValueError("أدخل الإنتاج السليم ووزنه الفعلي")
    if actual_output_weight + scrap_weight_kg > used_input_weight:
        raise ValueError("وزن الإنتاج والهالك لا يمكن أن يتجاوز وزن الخامات المستخدمة")
    average_input_cost = quantity(total_material_cost / used_input_weight)
    scrap_value = money(scrap_weight_kg * average_input_cost)
    finished_cost = money(max(Decimal("0"), total_material_cost - scrap_value))
    cost_per_good_kg = quantity(finished_cost / actual_output_weight)
    output_costs = _allocate_output_costs(
        outputs,
        finished_cost=finished_cost,
        cost_per_good_kg=cost_per_good_kg,
    )
    return CompletionPlan(
        actual_batches=actual_batches,
        full_batches=full_batches,
        modified_batches=modified_batches,
        good_output_quantity=quantity(good_quantity),
        defective_output_quantity=quantity(defective_quantity),
        actual_output_weight_kg=quantity(actual_output_weight),
        scrap_weight_kg=quantity(scrap_weight_kg),
        used_input_weight_kg=quantity(used_input_weight),
        full_mix_cost=full_mix_cost,
        modified_mix_cost=modified_mix_cost,
        total_material_cost=total_material_cost,
        average_input_cost_per_kg=average_input_cost,
        scrap_value=scrap_value,
        finished_cost=finished_cost,
        cost_per_good_kg=cost_per_good_kg,
        weight_variance_kg=quantity(used_input_weight - actual_output_weight - scrap_weight_kg),
        materials=tuple(material_usage),
        outputs=tuple(output_costs),
        adjustments=tuple(normalized_adjustments),
    )
