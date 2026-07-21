from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.wizard_manufacturing_repository import WizardManufacturingRepository
from app.services.production_completion_preview import calculate_completion_preview


def test_wizard_preview_uses_optional_scrap_that_was_actually_issued() -> None:
    preview = calculate_completion_preview(
        materials=[
            {
                "product_id": 1,
                "code": "RAW",
                "name": "خامة أساسية",
                "component_kind": "material",
                "quantity_per_batch": 200,
                "actual_quantity": 2000,
                "unit_cost": 2,
            },
            {
                "product_id": 2,
                "code": "SCRAP",
                "name": "كسر اختياري",
                "component_kind": "scrap",
                "quantity_per_batch": 100,
                "actual_quantity": 500,
                "unit_cost": 1,
            },
        ],
        actual_batches=10,
        outputs={
            3: {
                "good_quantity": 80,
                "defective_quantity": 0,
                "actual_weight_kg": 2400,
            }
        },
        scrap_weight=100,
        adjustments=[],
    )

    optional_scrap = next(row for row in preview["materials"] if row["product_id"] == 2)
    assert preview["full_batches"] == 10
    assert preview["modified_batches"] == 0
    assert optional_scrap["issued"] == pytest.approx(500)
    assert optional_scrap["used"] == pytest.approx(500)
    assert optional_scrap["unused"] == pytest.approx(0)
    assert preview["full_mix_cost"] == pytest.approx(4500)


def test_all_complete_order_skips_adjustments_and_returns_nothing(tmp_path: Path) -> None:
    database = Database(tmp_path / "all-complete.sqlite3")
    initialize_database(database)
    with database.session(immediate=True) as connection:
        warehouse = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        raw_a = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-A-FULL', 'خامة أ', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        raw_x = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-X-FULL', 'خامة X', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        pipe = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FG-28-FULL', 'ماسورة 28', 'finished_good', 'قطعة', 28)
                """
            ).lastrowid
        )
        for product_id, quantity, unit_cost in (
            (raw_a, 3000, 2),
            (raw_x, 2000, 5),
        ):
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, quantity_out,
                    unit_cost, reference_type, notes
                ) VALUES (?, ?, ?, 0, ?, 'test_stock', 'all complete acceptance')
                """,
                (product_id, warehouse, quantity, unit_cost),
            )

    repository = WizardManufacturingRepository(database)
    recipe = repository.create_recipe(
        code="MIX-FULL",
        name="خلطة كاملة",
        output_product_ids=[pipe],
        components=[
            {"product_id": raw_a, "quantity_per_batch": 200},
            {"product_id": raw_x, "quantity_per_batch": 100},
        ],
    )
    order = repository.create_order(
        recipe_id=recipe,
        warehouse_id=warehouse,
        outputs=[{"product_id": pipe, "quantity": 100}],
        scrap_inputs=[],
    )
    repository.start_order(order)
    values = {
        "actual_batches": 10,
        "outputs": {
            pipe: {
                "good_quantity": 100,
                "defective_quantity": 0,
                "actual_weight_kg": 2800,
            }
        },
        "scrap_weight": 200,
        "notes": "جميع الخلطات كاملة",
        "adjustments": [],
    }

    preview = repository.preview_order_completion(order, **values)
    assert preview["full_batches"] == 10
    assert preview["modified_batches"] == 0
    assert preview["full_mix_cost"] == pytest.approx(9000)
    assert preview["modified_mix_cost"] == pytest.approx(0)
    assert preview["returns"] == []

    result = repository.complete_order_with_mix_summary(order, **values)
    assert result["full_batches"] == 10
    assert result["modified_batches"] == 0
    assert result["returns"] == []
    summary = repository.get_mix_summary(order)
    assert summary["adjustments"] == []
    assert summary["outputs"][0]["good_quantity"] == pytest.approx(100)
    assert summary["outputs"][0]["actual_weight_kg"] == pytest.approx(2800)
