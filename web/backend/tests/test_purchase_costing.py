from decimal import Decimal

import pytest

from app.domain.purchasing.costing import calculate_receipt_cost, validate_partial_receipt


def test_purchase_loss_and_additional_cost_are_capitalized_over_net_amount() -> None:
    result = calculate_receipt_cost(
        gross_amount=Decimal("1000"),
        loss_amount=Decimal("5"),
        unit_price=Decimal("30"),
        additional_unit_cost=Decimal("4"),
    )

    assert result.net_amount == Decimal("995.000000")
    assert result.goods_cost == Decimal("30000.00")
    assert result.additional_cost == Decimal("4000.00")
    assert result.capitalized_cost == Decimal("34000.00")
    assert result.inventory_unit_cost == Decimal("34.170854")


def test_purchase_costing_rejects_total_loss_and_negative_cost() -> None:
    with pytest.raises(ValueError, match="الفاقد"):
        calculate_receipt_cost(
            gross_amount=Decimal("10"),
            loss_amount=Decimal("10"),
            unit_price=Decimal("2"),
        )
    with pytest.raises(ValueError, match="سالبتين"):
        calculate_receipt_cost(
            gross_amount=Decimal("10"),
            loss_amount=Decimal("0"),
            unit_price=Decimal("-1"),
        )


def test_partial_receipt_cannot_exceed_ordered_amount() -> None:
    assert validate_partial_receipt(
        ordered_amount=Decimal("100"),
        previously_received_amount=Decimal("40"),
        current_received_amount=Decimal("35"),
    ) == Decimal("25.000000")
    with pytest.raises(ValueError, match="يتجاوز"):
        validate_partial_receipt(
            ordered_amount=Decimal("100"),
            previously_received_amount=Decimal("80"),
            current_received_amount=Decimal("21"),
        )
