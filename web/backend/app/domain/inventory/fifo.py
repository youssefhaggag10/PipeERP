from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Literal

from app.domain.common.decimal import quantity

CostBasis = Literal["quantity", "weight"]


@dataclass(frozen=True, slots=True)
class FifoLayer:
    layer_id: str
    received_at: datetime
    sequence: int
    quantity_remaining: Decimal
    weight_remaining_kg: Decimal
    unit_cost: Decimal


@dataclass(frozen=True, slots=True)
class FifoAllocation:
    layer_id: str
    quantity: Decimal
    weight_kg: Decimal
    unit_cost: Decimal
    total_cost: Decimal


def allocate_fifo(
    *,
    layers: list[FifoLayer],
    amount: Decimal,
    cost_basis: CostBasis,
) -> tuple[FifoAllocation, ...]:
    """Allocate one stock dimension while preserving the paired dimension proportionally."""
    requested = quantity(amount)
    if requested <= 0:
        raise ValueError("كمية الصرف يجب أن تكون أكبر من صفر")
    if cost_basis not in ("quantity", "weight"):
        raise ValueError("أساس تكلفة المخزون غير صحيح")
    if any(
        layer.quantity_remaining < 0 or layer.weight_remaining_kg < 0 or layer.unit_cost < 0
        for layer in layers
    ):
        raise ValueError("طبقات المخزون تحتوي قيمة سالبة غير صالحة")

    ordered = sorted(layers, key=lambda layer: (layer.received_at, layer.sequence))
    available = sum(
        (
            layer.quantity_remaining if cost_basis == "quantity" else layer.weight_remaining_kg
            for layer in ordered
        ),
        Decimal("0"),
    )
    if available < requested:
        raise ValueError(f"الرصيد غير كافٍ. المتاح {available} والمطلوب {requested}")

    remaining = requested
    allocations: list[FifoAllocation] = []
    for layer in ordered:
        basis_available = (
            layer.quantity_remaining if cost_basis == "quantity" else layer.weight_remaining_kg
        )
        if remaining == 0:
            break
        if basis_available <= 0:
            continue
        allocated_basis = min(remaining, basis_available)
        if cost_basis == "quantity":
            allocated_quantity = allocated_basis
            allocated_weight = (
                quantity(layer.weight_remaining_kg * allocated_basis / basis_available)
                if layer.weight_remaining_kg > 0
                else Decimal("0")
            )
        else:
            allocated_weight = allocated_basis
            allocated_quantity = (
                quantity(layer.quantity_remaining * allocated_basis / basis_available)
                if layer.quantity_remaining > 0
                else Decimal("0")
            )
        allocations.append(
            FifoAllocation(
                layer_id=layer.layer_id,
                quantity=quantity(allocated_quantity),
                weight_kg=quantity(allocated_weight),
                unit_cost=layer.unit_cost,
                total_cost=quantity(allocated_basis * layer.unit_cost),
            )
        )
        remaining = quantity(remaining - allocated_basis)

    if remaining != 0:
        raise ValueError("الرصيد موجود لكن طبقات FIFO غير مكتملة")
    return tuple(allocations)
