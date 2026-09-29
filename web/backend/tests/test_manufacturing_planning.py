from decimal import Decimal

from app.domain.manufacturing.planning import (
    calculate_batch_plan,
    replan_for_available_scrap,
    target,
)


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


def test_stock_aware_replan_adds_batches_when_optional_scrap_is_short() -> None:
    plan = replan_for_available_scrap(
        target_weight_kg=Decimal("200"),
        base_material_kg_per_batch=Decimal("90"),
        scrap_quantities_kg_per_batch=[Decimal("10")],
        available_scrap_quantities_kg=[Decimal("0")],
        old_batches=2,
    )

    assert plan.changed is True
    assert plan.new_batches == 3
    assert plan.planned_scrap_kg == Decimal("30.000000")
    assert plan.usable_scrap_kg == Decimal("0.000000")
    assert plan.planned_input_weight_kg == Decimal("270.000000")


def test_stock_aware_replan_caps_each_scrap_source_at_its_own_stock() -> None:
    plan = replan_for_available_scrap(
        target_weight_kg=Decimal("205"),
        base_material_kg_per_batch=Decimal("90"),
        scrap_quantities_kg_per_batch=[Decimal("5"), Decimal("5")],
        available_scrap_quantities_kg=[Decimal("2"), Decimal("20")],
        old_batches=2,
    )

    assert plan.new_batches == 3
    assert plan.usable_scrap_kg == Decimal("17.000000")
    assert plan.planned_input_weight_kg == Decimal("287.000000")
