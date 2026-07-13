from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.manufacturing_repository import ManufacturingRepository
from app.services.manufacturing_planning_service import ProductionTarget, calculate_batch_plan


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "manufacturing.sqlite3")
    initialize_database(database)
    return database


def _masters(database: Database) -> dict[str, int]:
    with database.session() as connection:
        warehouse = int(
            connection.execute(
                "SELECT id FROM warehouses WHERE code = 'MAIN'"
            ).fetchone()[0]
        )
        raw_ids = []
        for code, name in (
            ("R1", "مخرز"),
            ("R2", "لحميات"),
            ("R3", "موحد"),
            ("R4", "ديكور"),
        ):
            raw_ids.append(
                int(
                    connection.execute(
                        """
                        INSERT INTO products(code, name, product_type, unit)
                        VALUES (?, ?, 'raw_material', 'كجم')
                        """,
                        (code, name),
                    ).lastrowid
                )
            )
        pipe_8 = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FG8', 'ري ضغوط A - 8 بوصة', 'finished_good', 'قطعة', 28)
                """
            ).lastrowid
        )
        pipe_6 = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FG6', 'ري ضغوط A - 6 بوصة', 'finished_good', 'قطعة', 18)
                """
            ).lastrowid
        )
        other_pipe = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FGB', 'صرف B', 'finished_good', 'قطعة', 10)
                """
            ).lastrowid
        )
    inventory = InventoryRepository(database)
    for index, product_id in enumerate(raw_ids, start=1):
        inventory.post_adjustment(
            product_id, 20_000, unit_cost=10 * index, lot_number=f"RAW-{index}"
        )
    return {
        "warehouse": warehouse,
        "pipe_8": pipe_8,
        "pipe_6": pipe_6,
        "other_pipe": other_pipe,
        **{f"raw_{index}": value for index, value in enumerate(raw_ids, start=1)},
    }


def test_shared_recipe_combines_pipe_sizes_and_rounds_batches_up() -> None:
    plan = calculate_batch_plan(
        [ProductionTarget(1, 100, 28), ProductionTarget(2, 200, 18)],
        [150, 50, 50, 25],
        [],
    )
    assert plan.target_weight == 6400
    assert plan.batch_weight == 275
    assert plan.batches == 24
    assert plan.planned_input_weight == 6600
    assert plan.expected_overage_weight == 200


def test_manufacturing_receives_extra_output_and_returns_costed_scrap(
    database: Database,
) -> None:
    data = _masters(database)
    repository = ManufacturingRepository(database)
    recipe_id = repository.create_recipe(
        code="IRR-A",
        name="ري ضغوط A",
        output_product_ids=[data["pipe_8"], data["pipe_6"]],
        components=[
            {"product_id": data["raw_1"], "quantity_per_batch": 150},
            {"product_id": data["raw_2"], "quantity_per_batch": 50},
            {"product_id": data["raw_3"], "quantity_per_batch": 50},
            {"product_id": data["raw_4"], "quantity_per_batch": 25},
        ],
        suggested_scrap_per_batch=50,
    )
    order_id = repository.create_order(
        recipe_id=recipe_id,
        warehouse_id=data["warehouse"],
        outputs=[
            {"product_id": data["pipe_8"], "quantity": 100},
            {"product_id": data["pipe_6"], "quantity": 200},
        ],
        scrap_inputs=[],
    )
    assert repository.get_order(order_id)["planned_batches"] == 24

    repository.start_order(order_id)
    result = repository.complete_order(
        order_id,
        actual_outputs={data["pipe_8"]: 102, data["pipe_6"]: 200},
        returned_scrap_quantity=100,
    )

    assert result["scrap_unit_cost"] > 0
    pipe_stock = database.fetch_one(
        """
        SELECT SUM(quantity_in - quantity_out) AS quantity
        FROM inventory_moves WHERE product_id = ?
        """,
        (data["pipe_8"],),
    )
    assert pipe_stock is not None and pipe_stock["quantity"] == 102
    scrap_stock = database.fetch_one(
        """
        SELECT im.product_id, SUM(im.quantity_in - im.quantity_out) AS quantity,
               MAX(im.unit_cost) AS unit_cost
        FROM inventory_moves im
        WHERE im.reference_type = 'manufacturing_scrap' AND im.reference_id = ?
        GROUP BY im.product_id
        """,
        (order_id,),
    )
    assert scrap_stock is not None
    assert scrap_stock["quantity"] == 100
    assert scrap_stock["unit_cost"] == pytest.approx(result["scrap_unit_cost"])


def test_scrap_from_one_recipe_can_be_used_by_another_at_original_fifo_cost(
    database: Database,
) -> None:
    data = _masters(database)
    repository = ManufacturingRepository(database)
    recipe_a = repository.create_recipe(
        code="A",
        name="خلطة A",
        output_product_ids=[data["pipe_8"]],
        components=[{"product_id": data["raw_1"], "quantity_per_batch": 100}],
    )
    order_a = repository.create_order(
        recipe_id=recipe_a,
        warehouse_id=data["warehouse"],
        outputs=[{"product_id": data["pipe_8"], "quantity": 3}],
    )
    repository.start_order(order_a)
    result_a = repository.complete_order(
        order_a,
        actual_outputs={data["pipe_8"]: 3},
        returned_scrap_quantity=10,
    )
    recipe_a_details = repository.get_recipe(recipe_a)
    source_scrap_id = int(recipe_a_details["scrap_product_id"])

    recipe_b = repository.create_recipe(
        code="B",
        name="خلطة B",
        output_product_ids=[data["other_pipe"]],
        components=[{"product_id": data["raw_2"], "quantity_per_batch": 90}],
    )
    order_b = repository.create_order(
        recipe_id=recipe_b,
        warehouse_id=data["warehouse"],
        outputs=[{"product_id": data["other_pipe"], "quantity": 9}],
        # Asking for more scrap than remains must never stop production.
        scrap_inputs=[{"product_id": source_scrap_id, "quantity_per_batch": 15}],
    )
    repository.start_order(order_b)
    material = next(
        row for row in repository.get_order(order_b)["materials"]
        if int(row["product_id"]) == source_scrap_id
    )
    assert material["planned_quantity"] == 15
    assert material["actual_quantity"] == 10
    assert material["unit_cost"] == pytest.approx(result_a["scrap_unit_cost"])
