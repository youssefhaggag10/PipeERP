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


def test_extra_batch_is_issued_automatically_when_order_is_completed(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "extra-batch-at-completion.sqlite3")
    initialize_database(database)
    with database.session(immediate=True) as connection:
        warehouse = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        raw_a = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-A-EXTRA', 'خامة أ', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        raw_b = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-B-EXTRA', 'خامة ب', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        pipe = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FG-28-EXTRA', 'ماسورة 28', 'finished_good', 'قطعة', 28)
                """
            ).lastrowid
        )
        for product_id, quantity, unit_cost in (
            (raw_a, 4000, 2),
            (raw_b, 2500, 5),
        ):
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, quantity_out,
                    unit_cost, reference_type, notes
                ) VALUES (?, ?, ?, 0, ?, 'test_stock', 'extra completion batch')
                """,
                (product_id, warehouse, quantity, unit_cost),
            )

    repository = WizardManufacturingRepository(database)
    recipe = repository.create_recipe(
        code="MIX-EXTRA",
        name="خلطة 325 كجم",
        output_product_ids=[pipe],
        components=[
            {"product_id": raw_a, "quantity_per_batch": 200},
            {"product_id": raw_b, "quantity_per_batch": 125},
        ],
    )
    order = repository.create_order(
        recipe_id=recipe,
        warehouse_id=warehouse,
        outputs=[{"product_id": pipe, "quantity": 100}],
        scrap_inputs=[],
    )
    repository.start_order(order)
    assert repository.get_order(order)["actual_batches"] == 9

    values = {
        "actual_batches": 10,
        "outputs": {
            pipe: {
                "good_quantity": 100,
                "defective_quantity": 0,
                "actual_weight_kg": 2800,
            }
        },
        "scrap_weight": 450,
        "notes": "خلطة إضافية بسبب هالك الماكينة",
        "adjustments": [],
    }
    preview = repository.preview_order_completion(order, **values)
    assert preview["issued_batches"] == 9
    assert preview["actual_batches"] == 10
    assert preview["used_input_weight"] == pytest.approx(3250)
    assert preview["scrap_weight"] == pytest.approx(450)

    result = repository.complete_order_with_mix_summary(order, **values)
    assert result["actual_batches"] == 10
    assert result["used_input_weight"] == pytest.approx(3250)
    assert result["weight_variance"] == pytest.approx(0)

    completed = repository.get_order(order)
    assert completed["actual_batches"] == 10
    issued_materials = {
        int(row["product_id"]): float(row["actual_quantity"])
        for row in completed["materials"]
    }
    assert issued_materials[raw_a] == pytest.approx(2000)
    assert issued_materials[raw_b] == pytest.approx(1250)


def test_extra_batch_shortage_rolls_back_completion_without_partial_issue(
    tmp_path: Path,
) -> None:
    database = Database(tmp_path / "extra-batch-shortage.sqlite3")
    initialize_database(database)
    with database.session(immediate=True) as connection:
        warehouse = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        raw = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-SHORT', 'خامة محدودة', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        pipe = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FG-SHORT', 'ماسورة محدودة', 'finished_good', 'قطعة', 28)
                """
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO inventory_moves(
                product_id, warehouse_id, quantity_in, quantity_out,
                unit_cost, reference_type, notes
            ) VALUES (?, ?, 2700, 0, 2, 'test_stock', 'exactly nine batches')
            """,
            (raw, warehouse),
        )

    repository = WizardManufacturingRepository(database)
    recipe = repository.create_recipe(
        code="MIX-SHORT",
        name="خلطة محدودة",
        output_product_ids=[pipe],
        components=[{"product_id": raw, "quantity_per_batch": 300}],
    )
    order = repository.create_order(
        recipe_id=recipe,
        warehouse_id=warehouse,
        outputs=[{"product_id": pipe, "quantity": 90}],
        scrap_inputs=[],
    )
    repository.start_order(order)

    with pytest.raises(ValueError, match="المخزون غير كاف|رصيد"):
        repository.complete_order_with_mix_summary(
            order,
            actual_batches=10,
            outputs={
                pipe: {
                    "good_quantity": 90,
                    "defective_quantity": 0,
                    "actual_weight_kg": 2520,
                }
            },
            scrap_weight=480,
            adjustments=[],
        )

    unchanged = repository.get_order(order)
    assert unchanged["status"] == "in_progress"
    assert unchanged["actual_batches"] == 9
    assert float(unchanged["materials"][0]["actual_quantity"]) == pytest.approx(2700)
