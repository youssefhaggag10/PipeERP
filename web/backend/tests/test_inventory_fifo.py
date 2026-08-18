from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.inventory.fifo import FifoLayer, allocate_fifo


def layer(
    layer_id: str,
    *,
    day: int,
    sequence: int,
    quantity: str,
    weight: str,
    unit_cost: str,
) -> FifoLayer:
    return FifoLayer(
        layer_id=layer_id,
        received_at=datetime(2026, 8, 1, tzinfo=UTC) + timedelta(days=day),
        sequence=sequence,
        quantity_remaining=Decimal(quantity),
        weight_remaining_kg=Decimal(weight),
        unit_cost=Decimal(unit_cost),
    )


def test_quantity_fifo_uses_oldest_layers_and_preserves_paired_weight() -> None:
    allocations = allocate_fifo(
        layers=[
            layer("new", day=2, sequence=2, quantity="10", weight="120", unit_cost="8"),
            layer("old", day=1, sequence=1, quantity="10", weight="100", unit_cost="5"),
        ],
        amount=Decimal("12"),
        cost_basis="quantity",
    )

    assert [(item.layer_id, item.quantity, item.weight_kg) for item in allocations] == [
        ("old", Decimal("10.000000"), Decimal("100.000000")),
        ("new", Decimal("2.000000"), Decimal("24.000000")),
    ]
    assert sum((item.total_cost for item in allocations), Decimal("0")) == Decimal("66.000000")


def test_weight_fifo_allocates_quantity_proportionally() -> None:
    allocations = allocate_fifo(
        layers=[layer("weight", day=1, sequence=1, quantity="10", weight="100", unit_cost="2")],
        amount=Decimal("25"),
        cost_basis="weight",
    )

    assert allocations[0].weight_kg == Decimal("25.000000")
    assert allocations[0].quantity == Decimal("2.500000")
    assert allocations[0].total_cost == Decimal("50.000000")


def test_fifo_rejects_insufficient_stock_and_invalid_layers() -> None:
    valid = layer("only", day=1, sequence=1, quantity="3", weight="0", unit_cost="4")
    with pytest.raises(ValueError, match="الرصيد غير كافٍ"):
        allocate_fifo(layers=[valid], amount=Decimal("4"), cost_basis="quantity")

    invalid = layer("negative", day=1, sequence=1, quantity="-1", weight="0", unit_cost="4")
    with pytest.raises(ValueError, match="قيمة سالبة"):
        allocate_fifo(layers=[invalid], amount=Decimal("1"), cost_basis="quantity")

    with pytest.raises(ValueError, match="أكبر من صفر"):
        allocate_fifo(layers=[valid], amount=Decimal("0"), cost_basis="quantity")
