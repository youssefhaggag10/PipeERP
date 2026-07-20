import sqlite3
from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.migrations import (
    DATABASE_VERSION,
    LATEST_SCHEMA_VERSION,
    MIGRATIONS,
    run_migrations,
)
from app.database.schema import initialize_database
from app.repositories.production_run_repository import ProductionRunRepository
from app.repositories.weight_sales_repository import WeightSalesRepository
from app.ui.appearance import AppearanceSettings, AppearanceSettingsRepository


@pytest.fixture
def database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "schema-v9.sqlite3")
    initialize_database(database)
    return database


def _apply_schema_through(connection: sqlite3.Connection, target_version: int) -> None:
    for version, migration in MIGRATIONS:
        if version > target_version:
            break
        migration(connection)
        connection.execute(f"PRAGMA user_version = {version}")


def _insert_product(
    connection: sqlite3.Connection,
    code: str,
    name: str,
    product_type: str,
    unit: str,
    *,
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


def _add_stock(
    connection: sqlite3.Connection,
    *,
    product_id: int,
    warehouse_id: int,
    quantity: float,
    unit_cost: float,
    reference_type: str = "test_stock",
) -> int:
    return int(
        connection.execute(
            """
            INSERT INTO inventory_moves(
                product_id, warehouse_id, quantity_in, quantity_out,
                unit_cost, reference_type, notes
            ) VALUES (?, ?, ?, 0, ?, ?, 'automated test stock')
            """,
            (product_id, warehouse_id, quantity, unit_cost, reference_type),
        ).lastrowid
    )


def _create_weight_layer(
    connection: sqlite3.Connection,
    *,
    product_id: int,
    warehouse_id: int,
    quantity: float,
    weight_kg: float,
    unit_cost: float,
) -> None:
    source_move_id = _add_stock(
        connection,
        product_id=product_id,
        warehouse_id=warehouse_id,
        quantity=quantity,
        unit_cost=unit_cost,
    )
    connection.execute(
        """
        INSERT INTO finished_good_weight_layers(
            product_id, warehouse_id, source_move_id,
            quantity_in, weight_in_kg, unit_cost_per_kg
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            product_id,
            warehouse_id,
            source_move_id,
            quantity,
            weight_kg,
            quantity * unit_cost / weight_kg,
        ),
    )


def _sales_masters(database: Database) -> dict[str, int]:
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        customer_id = int(
            connection.execute(
                """
                INSERT INTO partners(partner_type, code, name)
                VALUES ('customer', 'C-V9', 'عميل اختبارات الوزن')
                """
            ).lastrowid
        )
        pipe_28 = _insert_product(
            connection,
            "FG-28",
            "ماسورة 28 كجم",
            "finished_good",
            "قطعة",
            standard_weight_kg=28,
        )
        pipe_18 = _insert_product(
            connection,
            "FG-18",
            "ماسورة 18 كجم",
            "finished_good",
            "قطعة",
            standard_weight_kg=18,
        )
        _create_weight_layer(
            connection,
            product_id=pipe_28,
            warehouse_id=warehouse_id,
            quantity=100,
            weight_kg=2800,
            unit_cost=84,
        )
        _create_weight_layer(
            connection,
            product_id=pipe_18,
            warehouse_id=warehouse_id,
            quantity=100,
            weight_kg=1800,
            unit_cost=54,
        )
    return {
        "warehouse": warehouse_id,
        "customer": customer_id,
        "pipe_28": pipe_28,
        "pipe_18": pipe_18,
    }


def _order_line_ids(database: Database, order_id: int) -> list[int]:
    return [
        int(row["id"])
        for row in database.fetch_all(
            "SELECT id FROM sales_order_lines WHERE sales_order_id = ? ORDER BY id",
            (order_id,),
        )
    ]


def test_appearance_settings_round_trip_theme_font_and_scale(database: Database) -> None:
    repository = AppearanceSettingsRepository(database)

    repository.save_settings(AppearanceSettings(theme="light", font_size=17, scale_percent=125))

    assert repository.get_settings() == AppearanceSettings(
        theme="light",
        font_size=17,
        scale_percent=125,
    )


def test_upgrade_from_schema_8_to_9_preserves_existing_data() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _apply_schema_through(connection, 8)

    warehouse_id = int(
        connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
    )
    customer_id = int(
        connection.execute(
            "INSERT INTO partners(partner_type, code, name) VALUES ('customer', 'KEEP', 'بيانات محفوظة')"
        ).lastrowid
    )
    product_id = _insert_product(
        connection,
        "KEEP-FG",
        "ماسورة محفوظة",
        "finished_good",
        "قطعة",
        standard_weight_kg=28,
    )
    order_id = int(
        connection.execute(
            """
            INSERT INTO sales_orders(order_number, customer_id, warehouse_id, notes)
            VALUES ('SO-KEEP', ?, ?, 'must survive migration')
            """,
            (customer_id, warehouse_id),
        ).lastrowid
    )
    line_id = int(
        connection.execute(
            """
            INSERT INTO sales_order_lines(
                sales_order_id, product_id, quantity, unit, unit_price, line_total
            ) VALUES (?, ?, 7, 'قطعة', 100, 700)
            """,
            (order_id, product_id),
        ).lastrowid
    )
    connection.execute("PRAGMA user_version = 8")

    run_migrations(connection)

    assert connection.execute("PRAGMA user_version").fetchone()[0] == LATEST_SCHEMA_VERSION == 9
    assert connection.execute(
        "SELECT value FROM settings WHERE key = 'db_version'"
    ).fetchone()[0] == DATABASE_VERSION == "0.9.0"
    assert connection.execute(
        "SELECT name FROM products WHERE id = ?", (product_id,)
    ).fetchone()[0] == "ماسورة محفوظة"
    line = connection.execute(
        "SELECT quantity, line_total, billing_weight_kg, price_per_kg FROM sales_order_lines WHERE id = ?",
        (line_id,),
    ).fetchone()
    assert tuple(line) == (7, 700, 0, 0)
    order = connection.execute(
        "SELECT notes, billing_method, weight_card_total FROM sales_orders WHERE id = ?",
        (order_id,),
    ).fetchone()
    assert tuple(order) == ("must survive migration", "piece", 0)

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert {
        "manufacturing_runs",
        "manufacturing_run_materials",
        "manufacturing_run_outputs",
        "manufacturing_run_events",
        "finished_good_weight_layers",
        "sales_weight_cards",
        "sales_weight_card_lines",
        "sales_weight_inventory_allocations",
    }.issubset(tables)
    product_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(products)").fetchall()
    }
    assert "weight_tolerance_percent" in product_columns


def test_repository_initializers_do_not_create_v9_tables(tmp_path: Path) -> None:
    path = tmp_path / "schema-v8.sqlite3"
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    _apply_schema_through(connection, 8)
    connection.commit()
    connection.close()

    database = Database(path)
    ProductionRunRepository(database)
    WeightSalesRepository(database)

    with database.session() as check:
        tables = {
            row[0]
            for row in check.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "manufacturing_runs" not in tables
    assert "sales_weight_cards" not in tables


def test_independent_operating_mixes_preserve_history_cost_and_inventory(
    database: Database,
) -> None:
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        raw_a = _insert_product(connection, "RM-A", "خامة أ", "raw_material", "كجم")
        raw_b = _insert_product(connection, "RM-B", "خامة ب", "raw_material", "كجم")
        pipe = _insert_product(
            connection,
            "FG-100",
            "ماسورة تشغيل",
            "finished_good",
            "قطعة",
            standard_weight_kg=28,
        )
        _add_stock(
            connection,
            product_id=raw_a,
            warehouse_id=warehouse_id,
            quantity=2000,
            unit_cost=2,
        )
        _add_stock(
            connection,
            product_id=raw_b,
            warehouse_id=warehouse_id,
            quantity=2000,
            unit_cost=5,
        )

    repository = ProductionRunRepository(database)
    recipe_id = repository.create_recipe(
        code="RUN-RECIPE",
        name="خلطة تشغيل مستقلة",
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
    first_run_id = repository.ensure_current_run(order_id)
    first_issue = repository.issue_run(first_run_id, batches=1)
    first_result = repository.complete_run(
        first_run_id,
        outputs={pipe: {"quantity": 10, "actual_weight_kg": 280}},
        scrap_weight=20,
    )
    first_before_clone = repository.get_run(first_run_id)

    second_run_id = repository.clone_run_without_material(
        order_id,
        first_run_id,
        raw_b,
        "الخامة سببت مشكلة بعد أول عشر مواسير",
    )
    second_before_issue = repository.get_run(second_run_id)
    second_issue = repository.issue_run(second_run_id, batches=1)
    second_result = repository.complete_run(
        second_run_id,
        outputs={pipe: {"quantity": 7, "actual_weight_kg": 196}},
        scrap_weight=4,
    )
    summary = repository.close_order_from_runs(order_id)

    first_after_clone = repository.get_run(first_run_id)
    assert {int(row["product_id"]) for row in first_before_clone["materials"]} == {raw_a, raw_b}
    assert {int(row["product_id"]) for row in first_after_clone["materials"]} == {raw_a, raw_b}
    assert {int(row["product_id"]) for row in second_before_issue["materials"]} == {raw_a}

    assert first_issue["material_cost"] == pytest.approx(900)
    assert second_issue["material_cost"] == pytest.approx(400)
    assert first_result["finished_cost"] == pytest.approx(840)
    assert second_result["finished_cost"] == pytest.approx(392)
    assert first_result["cost_per_good_kg"] == pytest.approx(3)
    assert second_result["cost_per_good_kg"] == pytest.approx(2)

    assert summary["run_count"] == 2
    assert summary["material_cost"] == pytest.approx(1300)
    assert summary["finished_cost"] == pytest.approx(1232)
    assert summary["good_weight"] == pytest.approx(476)
    assert summary["scrap_weight"] == pytest.approx(24)
    assert summary["variance"] == pytest.approx(0)

    output = database.fetch_one(
        """
        SELECT actual_quantity FROM manufacturing_order_outputs
        WHERE manufacturing_order_id = ? AND product_id = ?
        """,
        (order_id, pipe),
    )
    stock = database.fetch_one(
        """
        SELECT COALESCE(SUM(quantity_in - quantity_out), 0) AS quantity
        FROM inventory_moves WHERE product_id = ?
        """,
        (pipe,),
    )
    layers = database.fetch_one(
        """
        SELECT SUM(quantity_in) AS quantity, SUM(weight_in_kg) AS weight
        FROM finished_good_weight_layers WHERE product_id = ?
        """,
        (pipe,),
    )
    assert output is not None and output["actual_quantity"] == pytest.approx(17)
    assert stock is not None and stock["quantity"] == pytest.approx(17)
    assert layers is not None and layers["quantity"] == pytest.approx(17)
    assert layers["weight"] == pytest.approx(476)


def test_single_size_weight_card_prices_and_deducts_pieces_and_weight(
    database: Database,
) -> None:
    data = _sales_masters(database)
    repository = WeightSalesRepository(database)
    order_id = repository.create_order_with_lines(
        customer_id=data["customer"],
        lines=[
            {
                "product_id": data["pipe_28"],
                "quantity": 10,
                "unit": "قطعة",
                "unit_price": 0,
            }
        ],
    )
    line_id = _order_line_ids(database, order_id)[0]

    card_id = repository.create_weight_card(
        order_id,
        lines=[{"sales_order_line_id": line_id, "quantity_pieces": 10}],
        net_weight_kg=275,
        price_per_kg=12,
    )

    card = repository.get_weight_card(card_id)
    assert card["total_amount"] == pytest.approx(275 * 12)
    assert card["lines"][0]["allocated_weight_kg"] == pytest.approx(275)
    order_line = database.fetch_one(
        """
        SELECT billing_weight_kg, price_per_kg, unit_price, line_total
        FROM sales_order_lines WHERE id = ?
        """,
        (line_id,),
    )
    assert order_line is not None
    assert order_line["billing_weight_kg"] == pytest.approx(275)
    assert order_line["price_per_kg"] == pytest.approx(12)
    assert order_line["unit_price"] == pytest.approx(330)
    assert order_line["line_total"] == pytest.approx(3300)

    repository.deliver_order(order_id)

    layer = database.fetch_one(
        """
        SELECT quantity_out, weight_out_kg
        FROM finished_good_weight_layers WHERE product_id = ?
        """,
        (data["pipe_28"],),
    )
    allocation = database.fetch_one(
        """
        SELECT SUM(quantity_pieces) AS quantity, SUM(weight_kg) AS weight
        FROM sales_weight_inventory_allocations
        """
    )
    sale_move = database.fetch_one(
        """
        SELECT SUM(quantity_out) AS quantity
        FROM inventory_moves
        WHERE reference_type = 'sale' AND reference_id = ? AND product_id = ?
        """,
        (order_id, data["pipe_28"]),
    )
    assert layer is not None and layer["quantity_out"] == pytest.approx(10)
    assert layer["weight_out_kg"] == pytest.approx(275)
    assert allocation is not None and allocation["quantity"] == pytest.approx(10)
    assert allocation["weight"] == pytest.approx(275)
    assert sale_move is not None and sale_move["quantity"] == pytest.approx(10)


def test_multi_size_card_distributes_actual_weight_by_standard_weight(
    database: Database,
) -> None:
    data = _sales_masters(database)
    repository = WeightSalesRepository(database)
    order_id = repository.create_order_with_lines(
        customer_id=data["customer"],
        lines=[
            {
                "product_id": data["pipe_28"],
                "quantity": 10,
                "unit": "قطعة",
                "unit_price": 0,
            },
            {
                "product_id": data["pipe_18"],
                "quantity": 20,
                "unit": "قطعة",
                "unit_price": 0,
            },
        ],
    )
    line_28, line_18 = _order_line_ids(database, order_id)

    card_id = repository.create_weight_card(
        order_id,
        lines=[
            {"sales_order_line_id": line_28, "quantity_pieces": 10},
            {"sales_order_line_id": line_18, "quantity_pieces": 20},
        ],
        net_weight_kg=620,
        price_per_kg=15,
    )

    card = repository.get_weight_card(card_id)
    lines = {int(line["sales_order_line_id"]): line for line in card["lines"]}
    theoretical_total = 10 * 28 + 20 * 18
    expected_28 = 620 * (10 * 28) / theoretical_total
    expected_18 = 620 * (20 * 18) / theoretical_total
    assert lines[line_28]["allocated_weight_kg"] == pytest.approx(expected_28)
    assert lines[line_18]["allocated_weight_kg"] == pytest.approx(expected_18)
    assert lines[line_28]["line_total"] == pytest.approx(expected_28 * 15)
    assert lines[line_18]["line_total"] == pytest.approx(expected_18 * 15)
    assert card["total_amount"] == pytest.approx(620 * 15)
    order = database.fetch_one(
        "SELECT billing_method, weight_card_total FROM sales_orders WHERE id = ?",
        (order_id,),
    )
    assert order is not None and order["billing_method"] == "weight"
    assert order["weight_card_total"] == pytest.approx(9300)


def test_weight_delivery_requires_complete_cards_and_piece_sales_still_work(
    database: Database,
) -> None:
    data = _sales_masters(database)
    repository = WeightSalesRepository(database)
    weight_order_id = repository.create_order_with_lines(
        customer_id=data["customer"],
        lines=[
            {
                "product_id": data["pipe_28"],
                "quantity": 10,
                "unit": "قطعة",
                "unit_price": 0,
            }
        ],
    )
    weight_line_id = _order_line_ids(database, weight_order_id)[0]
    repository.create_weight_card(
        weight_order_id,
        lines=[{"sales_order_line_id": weight_line_id, "quantity_pieces": 6}],
        net_weight_kg=165,
        price_per_kg=11,
    )

    with pytest.raises(ValueError, match="أكمل كروت الوزن"):
        repository.deliver_order(weight_order_id)

    repository.create_weight_card(
        weight_order_id,
        lines=[{"sales_order_line_id": weight_line_id, "quantity_pieces": 4}],
        net_weight_kg=110,
        price_per_kg=11,
    )
    repository.deliver_order(weight_order_id)
    assert database.fetch_one(
        "SELECT status FROM sales_orders WHERE id = ?", (weight_order_id,)
    )["status"] == "delivered"

    piece_order_id = repository.create_order_with_lines(
        customer_id=data["customer"],
        lines=[
            {
                "product_id": data["pipe_18"],
                "quantity": 5,
                "unit": "قطعة",
                "unit_price": 100,
            }
        ],
    )
    piece_before = database.fetch_one(
        "SELECT billing_method, weight_card_total FROM sales_orders WHERE id = ?",
        (piece_order_id,),
    )
    repository.deliver_order(piece_order_id)
    piece_line = database.fetch_one(
        "SELECT unit_price, line_total FROM sales_order_lines WHERE sales_order_id = ?",
        (piece_order_id,),
    )
    piece_after = database.fetch_one(
        "SELECT status, billing_method FROM sales_orders WHERE id = ?",
        (piece_order_id,),
    )
    assert piece_before is not None and tuple(piece_before) == ("piece", 0)
    assert piece_line is not None and tuple(piece_line) == (100, 500)
    assert piece_after is not None and tuple(piece_after) == ("delivered", "piece")
