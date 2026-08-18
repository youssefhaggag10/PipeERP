from decimal import Decimal

from app.domain.manufacturing.planning import calculate_batch_plan, target


def test_batch_plan_includes_reused_scrap_in_planned_input() -> None:
    plan = calculate_batch_plan(
        targets=[target(1, "100", "1.25"), target(2, "50", "0.5")],
        material_quantities_kg=[Decimal("90")],
        reused_scrap_quantities_kg=[Decimal("10")],
    )

    assert plan.target_weight_kg == Decimal("150.000000")
    assert plan.batches == 2
    assert plan.planned_input_weight_kg == Decimal("200.000000")
    assert plan.expected_overage_kg == Decimal("50.000000")


def test_batch_plan_rejects_missing_base_material() -> None:
    try:
        calculate_batch_plan(
            targets=[target(1, "10", "1")],
            material_quantities_kg=[],
        )
    except ValueError as exc:
        assert "خامة أساسية" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_batch_plan_rejects_missing_targets() -> None:
    try:
        calculate_batch_plan(targets=[], material_quantities_kg=[Decimal("10")])
    except ValueError as exc:
        assert "منتجًا نهائيًا" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_batch_plan_rejects_non_positive_target() -> None:
    try:
        calculate_batch_plan(
            targets=[target(1, "0", "1")],
            material_quantities_kg=[Decimal("10")],
        )
    except ValueError as exc:
        assert "أكبر من صفر" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_batch_plan_rejects_negative_reused_scrap() -> None:
    try:
        calculate_batch_plan(
            targets=[target(1, "10", "1")],
            material_quantities_kg=[Decimal("10")],
            reused_scrap_quantities_kg=[Decimal("-1")],
        )
    except ValueError as exc:
        assert "سالبة" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
