from decimal import Decimal

from app.domain.sales.weight_card import calculate_weight_card, line


def test_total_card_absorbs_weight_and_money_rounding_in_last_line() -> None:
    result = calculate_weight_card(
        lines=[line(1, "3", "1"), line(2, "2", "1")],
        weight_mode="total_card",
        pricing_mode="uniform",
        total_actual_weight_kg=Decimal("10"),
        uniform_price_per_kg=Decimal("7.333"),
    )

    assert result.total_weight_kg == Decimal("10.000000")
    assert sum(item.allocated_weight_kg for item in result.lines) == Decimal("10.000000")
    assert result.subtotal == Decimal("73.33")
    assert sum(item.line_total for item in result.lines) == Decimal("73.33")


def test_per_line_weight_requires_every_actual_weight() -> None:
    try:
        calculate_weight_card(
            lines=[line(1, "2", "1")],
            weight_mode="per_line",
            pricing_mode="uniform",
            uniform_price_per_kg=Decimal("10"),
        )
    except ValueError as exc:
        assert "الوزن الفعلي" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_per_line_weight_and_pricing_calculate_individual_totals() -> None:
    result = calculate_weight_card(
        lines=[
            line(1, "2", "1", actual_weight_kg="2.4", price_per_kg="10"),
            line(2, "3", "0.5", actual_weight_kg="1.6", price_per_kg="12.5"),
        ],
        weight_mode="per_line",
        pricing_mode="per_line",
    )

    assert result.total_weight_kg == Decimal("4.000000")
    assert result.subtotal == Decimal("44.00")


def test_weight_card_rejects_empty_or_invalid_lines() -> None:
    for lines in ([], [line(1, "0", "1")]):
        try:
            calculate_weight_card(
                lines=lines,
                weight_mode="total_card",
                pricing_mode="uniform",
                total_actual_weight_kg=Decimal("10"),
                uniform_price_per_kg=Decimal("10"),
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError")


def test_weight_card_rejects_invalid_modes_and_prices() -> None:
    valid_line = [line(1, "1", "1", actual_weight_kg="1")]
    invalid_inputs = [
        {"weight_mode": "unknown", "pricing_mode": "uniform", "uniform_price_per_kg": Decimal("1")},
        {"weight_mode": "total_card", "pricing_mode": "uniform", "uniform_price_per_kg": None},
        {"weight_mode": "total_card", "pricing_mode": "unknown", "uniform_price_per_kg": None},
        {"weight_mode": "total_card", "pricing_mode": "per_line", "uniform_price_per_kg": None},
    ]
    for values in invalid_inputs:
        try:
            calculate_weight_card(
                lines=valid_line,
                weight_mode=values["weight_mode"],  # type: ignore[arg-type]
                pricing_mode=values["pricing_mode"],  # type: ignore[arg-type]
                total_actual_weight_kg=Decimal("1"),
                uniform_price_per_kg=values["uniform_price_per_kg"],
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError")
