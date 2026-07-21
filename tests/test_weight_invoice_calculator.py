import pytest

from app.services.weight_invoice_calculator import (
    calculate_net_weight,
    calculate_weight_invoice,
)


def test_total_card_weight_is_distributed_without_rounding_loss() -> None:
    result = calculate_weight_invoice(
        lines=[
            {"product_id": 1, "quantity": 3, "standard_weight_kg": 10},
            {"product_id": 2, "quantity": 2, "standard_weight_kg": 15},
            {"product_id": 3, "quantity": 1, "standard_weight_kg": 7},
        ],
        weight_mode="total_card",
        pricing_mode="uniform",
        total_actual_weight_kg=100,
        uniform_price_per_kg=25,
    )

    assert sum(line["allocated_weight_kg"] for line in result["lines"]) == pytest.approx(100)
    assert result["subtotal"] == pytest.approx(2500)
    assert result["total_pieces"] == pytest.approx(6)


def test_per_line_weight_and_individual_prices_drive_invoice_value() -> None:
    result = calculate_weight_invoice(
        lines=[
            {
                "product_id": 1,
                "quantity": 4,
                "standard_weight_kg": 10,
                "actual_weight_kg": 38.5,
                "price_per_kg": 20,
            },
            {
                "product_id": 2,
                "quantity": 2,
                "standard_weight_kg": 15,
                "actual_weight_kg": 31.25,
                "price_per_kg": 24,
            },
        ],
        weight_mode="per_line",
        pricing_mode="per_line",
    )

    assert result["total_actual_weight_kg"] == pytest.approx(69.75)
    assert result["lines"][0]["line_total"] == pytest.approx(770)
    assert result["lines"][1]["line_total"] == pytest.approx(750)
    assert result["subtotal"] == pytest.approx(1520)


def test_total_card_can_use_different_price_for_each_allocated_line() -> None:
    result = calculate_weight_invoice(
        lines=[
            {
                "product_id": 1,
                "quantity": 1,
                "standard_weight_kg": 10,
                "price_per_kg": 20,
            },
            {
                "product_id": 2,
                "quantity": 1,
                "standard_weight_kg": 30,
                "price_per_kg": 30,
            },
        ],
        weight_mode="total_card",
        pricing_mode="per_line",
        total_actual_weight_kg=80,
    )

    assert [line["allocated_weight_kg"] for line in result["lines"]] == pytest.approx(
        [20, 60]
    )
    assert result["subtotal"] == pytest.approx(2200)


def test_vehicle_scale_calculates_net_weight() -> None:
    assert calculate_net_weight(
        use_vehicle_scale=True,
        gross_weight_kg=8200,
        tare_weight_kg=5100,
    ) == pytest.approx(3100)


def test_missing_actual_weight_is_rejected() -> None:
    with pytest.raises(ValueError, match="الوزن الفعلي"):
        calculate_weight_invoice(
            lines=[{"product_id": 1, "quantity": 2, "standard_weight_kg": 10}],
            weight_mode="per_line",
            pricing_mode="uniform",
            uniform_price_per_kg=20,
        )
