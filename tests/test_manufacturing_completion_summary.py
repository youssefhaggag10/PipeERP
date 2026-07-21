from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.wizard_manufacturing_repository import WizardManufacturingRepository


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "manufacturing-summary.sqlite3")
    initialize_database(database)
    return database


def _insert_product(
    connection,
    *,
    code: str,
    name: str,
    product_type: str,
    unit: str,
    standard_weight_kg: float = 0,
) -> int:
    return int(
        connection.execute(
            """
            INSERT INTO products(
                code, name, product_type, unit, standard_weight_kg
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (code, name, product_type, unit, standard_weight_kg),
        ).lastrowid
    )


def _stock(connection, product_id: int, warehouse_id: int, quantity: float, unit_cost: float) -> None:
    connection.execute(
        """
        INSERT INTO inventory_moves(
            product_id, warehouse_id, quantity_in, quantity_out,
            unit_cost, reference_type, notes
        ) VALUES (?, ?, ?, 0, ?, 'test_stock', 'completion summary test')
        """,
        (product_id, warehouse_id, quantity, unit_cost),
    )


def test_order_completion_records_mix_summary_and_returns_unused_materials(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute(
                "SELECT id FROM warehouses WHERE code = 'MAIN'"
            ).fetchone()[0]
        )
        raw_a = _insert_product(
            connection,
            code="RAW-A",
            name="خامة أ",
            product_type="raw_material",
            unit="كجم",
        )
        raw_b = _insert_product(
            connection,
            code="RAW-B",
            name="خامة ب",
            product_type="raw_material",
            unit="كجم",
        )
        pipe = _insert_product(
            connection,
            code="FG-28",
            name="ماسورة 28",
            product_type="finished_good",
            unit="قطعة",
            standard_weight_kg=28,
        )
        _stock(connection, raw_a, warehouse_id, 3000, 2)
        _stock(connection, raw_b, warehouse_id, 2000, 5)

    repository = WizardManufacturingRepository(database)
    recipe_id = repository.create_recipe(
        code="MIX-SUMMARY",
        name="خلطة تقرير مجمع",
        output_product_ids=[pipe],
        components=[
            {"product_id": raw_a, "quantity_per_batch": 200},
            {"product_id": raw_b, "quantity_per_batch": 100},
        ],
    )
    order_id = repository.create_order(
        recipe_id=recipe_id,
        warehouse_id=warehouse_id,
        outputs=[{"product_id": pipe, "quantity": 100}],
        scrap_inputs=[],
    )

    repository.start_order(order_id)
    started = repository.get_order(order_id)
    assert started["status"] == "in_progress"
    assert started["actual_batches"] == 10
    assert database.fetch_one(
        "SELECT COUNT(*) AS n FROM manufacturing_runs WHERE manufacturing_order_id = ?",
        (order_id,),
    )["n"] == 0

    adjustments = [
        {
            "excluded_product_id": raw_b,
            "batch_count": 3,
            "reason": "تسببت في عيب بالإنتاج",
            "actual_material_quantities": {raw_a: 600},
        }
    ]
    outputs = {
        pipe: {
            "good_quantity": 95,
            "defective_quantity": 5,
            "actual_weight_kg": 2660,
        }
    }
    preview = repository.preview_order_completion(
        order_id,
        actual_batches=10,
        outputs=outputs,
        scrap_weight=40,
        notes="تم استبعاد خامة ب من آخر ثلاث خلطات",
        adjustments=adjustments,
    )
    assert preview["full_batches"] == 7
    assert preview["modified_batches"] == 3
    assert preview["full_mix_cost"] == pytest.approx(6300)
    assert preview["modified_mix_cost"] == pytest.approx(1200)
    assert preview["total_cost"] == pytest.approx(7500)
    assert preview["returns"][0]["product_id"] == raw_b
    assert preview["returns"][0]["unused_quantity"] == pytest.approx(300)

    result = repository.complete_order_with_mix_summary(
        order_id,
        actual_batches=10,
        outputs=outputs,
        scrap_weight=40,
        notes="تم استبعاد خامة ب من آخر ثلاث خلطات",
        adjustments=adjustments,
    )

    assert result["full_mix_cost"] == pytest.approx(6300)
    assert result["modified_mix_cost"] == pytest.approx(1200)
    assert result["total_cost"] == pytest.approx(7500)
    assert result["actual_output_weight"] == pytest.approx(2660)
    assert result["weight_variance"] == pytest.approx(0)

    completed = repository.get_order(order_id)
    assert completed["status"] == "completed"
    assert completed["actual_batches"] == 10
    assert completed["material_cost"] == pytest.approx(7500)

    raw_b_material = database.fetch_one(
        """
        SELECT actual_quantity, total_cost
        FROM manufacturing_order_materials
        WHERE manufacturing_order_id = ? AND product_id = ?
        """,
        (order_id, raw_b),
    )
    assert tuple(raw_b_material) == pytest.approx((700, 3500))

    raw_b_balance = database.fetch_one(
        """
        SELECT SUM(quantity_in - quantity_out) AS balance
        FROM inventory_moves
        WHERE product_id = ? AND warehouse_id = ?
        """,
        (raw_b, warehouse_id),
    )
    assert raw_b_balance["balance"] == pytest.approx(1300)

    layer = database.fetch_one(
        """
        SELECT quantity_in, weight_in_kg
        FROM finished_good_weight_layers
        WHERE product_id = ?
        """,
        (pipe,),
    )
    assert tuple(layer) == pytest.approx((95, 2660))

    summary = repository.get_mix_summary(order_id)
    assert summary["planned_batches"] == 10
    assert summary["full_batches"] == 7
    assert summary["modified_batches"] == 3
    assert summary["good_output_quantity"] == pytest.approx(95)
    assert summary["defective_output_quantity"] == pytest.approx(5)
    assert summary["outputs"][0]["actual_weight_kg"] == pytest.approx(2660)
    assert summary["returns"][0]["product_id"] == raw_b
    assert summary["returns"][0]["unused_quantity"] == pytest.approx(300)
    assert summary["adjustments"][0]["name"] == "خامة ب"
    assert summary["adjustments"][0]["excluded_batches"] == 3
    assert "خامة أ" in summary["adjustments"][0]["actual_materials_text"]
