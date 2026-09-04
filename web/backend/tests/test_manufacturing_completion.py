from decimal import Decimal

import pytest

from app.domain.manufacturing.completion import (
    CompletionMaterial,
    CompletionOutput,
    MixAdjustment,
    calculate_completion_plan,
)


def material(
    product_id: str,
    per_batch: str,
    issued: str,
    cost: str,
    *,
    kind: str = "material",
) -> CompletionMaterial:
    return CompletionMaterial(
        product_id=product_id,
        name=product_id,
        component_kind=kind,
        quantity_per_batch=Decimal(per_batch),
        issued_quantity=Decimal(issued),
        unit_cost=Decimal(cost),
    )


def output(product_id: str, good: str, defective: str, weight: str) -> CompletionOutput:
    return CompletionOutput(
        product_id=product_id,
        name=product_id,
        good_quantity=Decimal(good),
        defective_quantity=Decimal(defective),
        actual_weight_kg=Decimal(weight),
    )


def test_completion_matches_desktop_cost_and_scrap_formulas() -> None:
    plan = calculate_completion_plan(
        actual_batches=2,
        issued_batches=2,
        materials=[
            material("PVC", "90", "180", "2"),
            material("SCRAP", "10", "20", "1", kind="scrap"),
        ],
        outputs=[output("PIPE-A", "100", "2", "150"), output("PIPE-B", "50", "1", "25")],
        scrap_weight_kg=Decimal("15"),
    )

    assert plan.used_input_weight_kg == Decimal("200.000000")
    assert plan.total_material_cost == Decimal("380.00")
    assert plan.average_input_cost_per_kg == Decimal("1.900000")
    assert plan.scrap_value == Decimal("28.50")
    assert plan.finished_cost == Decimal("351.50")
    assert plan.weight_variance_kg == Decimal("10.000000")
    assert sum((line.line_cost for line in plan.outputs), Decimal("0")) == Decimal("351.50")


def test_modified_mix_excludes_material_and_returns_unused_quantity() -> None:
    plan = calculate_completion_plan(
        actual_batches=3,
        issued_batches=3,
        materials=[material("A", "60", "180", "2"), material("B", "40", "120", "3")],
        outputs=[output("PIPE", "100", "0", "220")],
        scrap_weight_kg=Decimal("0"),
        adjustments=[
            MixAdjustment(
                excluded_product_id="B",
                batch_count=1,
                reason="خلطة اختبار بدون B",
                actual_material_quantities={"A": Decimal("55")},
            )
        ],
    )

    usage = {item.product_id: item for item in plan.materials}
    assert plan.full_batches == 2
    assert plan.modified_batches == 1
    assert usage["A"].used_quantity == Decimal("175.000000")
    assert usage["A"].unused_quantity == Decimal("5.000000")
    assert usage["B"].used_quantity == Decimal("80.000000")
    assert usage["B"].unused_quantity == Decimal("40.000000")
    assert plan.full_mix_cost == Decimal("480.00")
    assert plan.modified_mix_cost == Decimal("110.00")


def test_optional_scrap_uses_only_what_was_actually_issued() -> None:
    plan = calculate_completion_plan(
        actual_batches=2,
        issued_batches=2,
        materials=[
            material("BASE", "90", "180", "1"),
            material("SCRAP", "10", "8", "1", kind="scrap"),
        ],
        outputs=[output("PIPE", "90", "0", "180")],
        scrap_weight_kg=Decimal("0"),
    )

    usage = {item.product_id: item for item in plan.materials}
    assert usage["SCRAP"].used_quantity == Decimal("8.000000")
    assert plan.used_input_weight_kg == Decimal("188.000000")


def test_completion_rejects_usage_above_issued_quantity() -> None:
    with pytest.raises(ValueError, match="يتجاوز المصروف"):
        calculate_completion_plan(
            actual_batches=2,
            issued_batches=1,
            materials=[material("BASE", "100", "100", "1")],
            outputs=[output("PIPE", "10", "0", "90")],
        )


def test_completion_rejects_output_and_scrap_above_used_inputs() -> None:
    with pytest.raises(ValueError, match="لا يمكن أن يتجاوز"):
        calculate_completion_plan(
            actual_batches=1,
            issued_batches=1,
            materials=[material("BASE", "100", "100", "1")],
            outputs=[output("PIPE", "10", "0", "95")],
            scrap_weight_kg=Decimal("6"),
        )


def test_modified_batches_cannot_exceed_actual_batches() -> None:
    with pytest.raises(ValueError, match="مجموع الخلطات المعدلة"):
        calculate_completion_plan(
            actual_batches=1,
            issued_batches=1,
            materials=[material("BASE", "100", "100", "1")],
            outputs=[output("PIPE", "10", "0", "90")],
            adjustments=[
                MixAdjustment(
                    excluded_product_id="BASE",
                    batch_count=2,
                    reason="اختبار",
                    actual_material_quantities={},
                )
            ],
        )
