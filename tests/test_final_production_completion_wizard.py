import pytest

from app.services.completion_scrap_calculator import (
    calculate_completion_input_weight,
    calculate_suggested_scrap_weight,
)
from app.services.material_quantity_defaults import default_actual_material_quantities


def _materials() -> list[dict]:
    return [
        {
            "product_id": 1,
            "name": "خامة أ",
            "component_kind": "material",
            "quantity_per_batch": 200,
            "actual_quantity": 2000,
        },
        {
            "product_id": 2,
            "name": "خامة X",
            "component_kind": "material",
            "quantity_per_batch": 100,
            "actual_quantity": 1000,
        },
    ]


def test_adjustment_defaults_cap_optional_scrap_to_issued_quantity() -> None:
    materials = [
        {
            "product_id": 1,
            "component_kind": "material",
            "quantity_per_batch": 200,
            "actual_quantity": 2000,
        },
        {
            "product_id": 2,
            "component_kind": "scrap",
            "quantity_per_batch": 100,
            "actual_quantity": 500,
        },
        {
            "product_id": 3,
            "component_kind": "material",
            "quantity_per_batch": 25,
            "actual_quantity": 250,
        },
    ]

    defaults = default_actual_material_quantities(
        materials,
        excluded_product_id=3,
        batch_count=3,
        issued_batches=10,
    )

    assert defaults[1] == pytest.approx(600)
    assert defaults[2] == pytest.approx(150)
    assert 3 not in defaults


def test_adjustment_defaults_never_exceed_recipe_scrap_rate() -> None:
    defaults = default_actual_material_quantities(
        [
            {
                "product_id": 9,
                "component_kind": "scrap",
                "quantity_per_batch": 50,
                "actual_quantity": 900,
            }
        ],
        excluded_product_id=99,
        batch_count=4,
        issued_batches=10,
    )

    assert defaults[9] == pytest.approx(200)


def test_scrap_recalculates_when_batches_or_output_change() -> None:
    ten_batches = calculate_suggested_scrap_weight(
        materials=_materials(),
        actual_batches=10,
        issued_batches=10,
        output_weights={3: 2800},
    )
    nine_batches = calculate_suggested_scrap_weight(
        materials=_materials(),
        actual_batches=9,
        issued_batches=10,
        output_weights={3: 2520},
    )

    assert ten_batches == pytest.approx(200)
    assert nine_batches == pytest.approx(180)


def test_modified_batches_reduce_input_and_scrap_automatically() -> None:
    adjustments = [
        {
            "excluded_product_id": 2,
            "batch_count": 3,
            "actual_material_quantities": {1: 600},
        }
    ]
    input_weight = calculate_completion_input_weight(
        materials=_materials(),
        actual_batches=10,
        issued_batches=10,
        adjustments=adjustments,
    )
    scrap = calculate_suggested_scrap_weight(
        materials=_materials(),
        actual_batches=10,
        issued_batches=10,
        output_weights={3: 2660},
        adjustments=adjustments,
    )

    assert input_weight == pytest.approx(2700)
    assert scrap == pytest.approx(40)
