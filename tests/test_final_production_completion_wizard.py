import pytest

from app.services.material_quantity_defaults import default_actual_material_quantities


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
