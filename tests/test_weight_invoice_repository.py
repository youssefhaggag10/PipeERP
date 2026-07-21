from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.sales_repository import SalesRepository
from app.repositories.weight_invoice_repository import WeightInvoiceRepository


def _seed_finished_product(
    database: Database,
    *,
    code: str,
    name: str,
    standard_weight: float,
    quantity: float,
    actual_weight: float,
) -> int:
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES (?, ?, 'finished_good', 'ماسورة', ?)
                """,
                (code, name, standard_weight),
            ).lastrowid
        )
        move_id = int(
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, quantity_out,
                    unit_cost, reference_type, notes
                ) VALUES (?, ?, ?, 0, 100, 'manufacturing', 'رصيد اختبار')
                """,
                (product_id, warehouse_id, quantity),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO finished_good_weight_layers(
                product_id, warehouse_id, source_move_id,
                quantity_in, weight_in_kg, unit_cost_per_kg
            ) VALUES (?, ?, ?, ?, ?, 10)
            """,
            (product_id, warehouse_id, move_id, quantity, actual_weight),
        )
        return product_id


def _customer(database: Database) -> int:
    with database.session(immediate=True) as connection:
        return int(
            connection.execute(
                "INSERT INTO partners(partner_type, code, name) "
                "VALUES ('customer', 'C-1', 'عميل الوزن')"
            ).lastrowid
        )


def test_standard_piece_sale_still_uses_original_path(tmp_path: Path) -> None:
    database = Database(tmp_path / "piece.sqlite3")
    initialize_database(database)
    customer_id = _customer(database)
    product_id = _seed_finished_product(
        database,
        code="P-1",
        name="ماسورة عادية",
        standard_weight=10,
        quantity=20,
        actual_weight=200,
    )

    repository = SalesRepository(database)
    order_id = repository.create_order(customer_id, product_id, 2, "ماسورة", 150)
    repository.deliver_order(order_id)

    order = database.fetch_one(
        "SELECT status, billing_method FROM sales_orders WHERE id = ?",
        (order_id,),
    )
    assert order["status"] == "delivered"
    assert order["billing_method"] == "piece"


def test_weight_invoice_draft_and_approval_post_count_weight_and_debt(tmp_path: Path) -> None:
    database = Database(tmp_path / "weight.sqlite3")
    initialize_database(database)
    customer_id = _customer(database)
    product_id = _seed_finished_product(
        database,
        code="W-1",
        name="ماسورة 90 مللي 6 بار",
        standard_weight=10,
        quantity=100,
        actual_weight=1000,
    )
    repository = WeightInvoiceRepository(database)

    draft = repository.create_weight_sale_draft(
        customer_id=customer_id,
        lines=[{"product_id": product_id, "quantity": 10}],
        weight_mode="total_card",
        pricing_mode="uniform",
        net_weight_kg=95,
        uniform_price_per_kg=20,
        vehicle_number="س ص ع 123",
    )

    assert draft["card_number"] == "WC000001"
    assert database.fetch_one(
        "SELECT id FROM sales_invoices WHERE sales_order_id = ?",
        (draft["order_id"],),
    ) is None

    approved = repository.approve_weight_sale(draft["order_id"])
    invoice = database.fetch_one(
        "SELECT * FROM sales_invoices WHERE id = ?",
        (approved["invoice_id"],),
    )
    assert invoice["status"] == "posted"
    assert invoice["invoice_type"] == "weight"
    assert float(invoice["total"]) == pytest.approx(1900)
    assert float(invoice["net_total"]) == pytest.approx(1900)

    quantity_out = database.fetch_one(
        """
        SELECT SUM(quantity_out) AS value FROM inventory_moves
        WHERE product_id = ? AND reference_type = 'sale'
        """,
        (product_id,),
    )
    weight_out = database.fetch_one(
        "SELECT weight_out_kg FROM finished_good_weight_layers WHERE product_id = ?",
        (product_id,),
    )
    assert float(quantity_out["value"]) == pytest.approx(10)
    assert float(weight_out["weight_out_kg"]) == pytest.approx(95)


def test_multi_size_card_preserves_total_allocated_weight(tmp_path: Path) -> None:
    database = Database(tmp_path / "mixed.sqlite3")
    initialize_database(database)
    customer_id = _customer(database)
    first = _seed_finished_product(
        database,
        code="W-90",
        name="ماسورة 90 مللي",
        standard_weight=10,
        quantity=50,
        actual_weight=500,
    )
    second = _seed_finished_product(
        database,
        code="W-125",
        name="ماسورة 125 مللي",
        standard_weight=20,
        quantity=50,
        actual_weight=1000,
    )
    repository = WeightInvoiceRepository(database)

    draft = repository.create_weight_sale_draft(
        customer_id=customer_id,
        lines=[
            {"product_id": first, "quantity": 3},
            {"product_id": second, "quantity": 4},
        ],
        weight_mode="total_card",
        pricing_mode="uniform",
        net_weight_kg=111.111111,
        uniform_price_per_kg=30,
    )
    lines = database.fetch_all(
        """
        SELECT allocated_weight_kg FROM sales_weight_card_lines
        WHERE weight_card_id = ? ORDER BY id
        """,
        (draft["card_id"],),
    )
    assert sum(float(line["allocated_weight_kg"]) for line in lines) == pytest.approx(
        111.111111
    )


def test_per_line_weight_and_price_are_saved_and_approved(tmp_path: Path) -> None:
    database = Database(tmp_path / "per-line.sqlite3")
    initialize_database(database)
    customer_id = _customer(database)
    first = _seed_finished_product(
        database,
        code="L-1",
        name="مقاس أول",
        standard_weight=10,
        quantity=20,
        actual_weight=200,
    )
    second = _seed_finished_product(
        database,
        code="L-2",
        name="مقاس ثان",
        standard_weight=15,
        quantity=20,
        actual_weight=300,
    )
    repository = WeightInvoiceRepository(database)

    draft = repository.create_weight_sale_draft(
        customer_id=customer_id,
        lines=[
            {
                "product_id": first,
                "quantity": 2,
                "actual_weight_kg": 19,
                "price_per_kg": 20,
                "notes": "أول",
            },
            {
                "product_id": second,
                "quantity": 2,
                "actual_weight_kg": 31,
                "price_per_kg": 25,
                "notes": "ثان",
            },
        ],
        weight_mode="per_line",
        pricing_mode="per_line",
    )
    approved = repository.approve_weight_sale(draft["order_id"])
    assert approved["net_total"] == pytest.approx(1155)
    stored = database.fetch_all(
        """
        SELECT actual_weight_kg, price_per_kg, line_total, notes
        FROM sales_weight_card_lines WHERE weight_card_id = ? ORDER BY id
        """,
        (draft["card_id"],),
    )
    assert [float(row["actual_weight_kg"]) for row in stored] == pytest.approx([19, 31])
    assert [float(row["price_per_kg"]) for row in stored] == pytest.approx([20, 25])
    assert [float(row["line_total"]) for row in stored] == pytest.approx([380, 775])


def test_approval_without_actual_weight_stock_is_rejected_atomically(tmp_path: Path) -> None:
    database = Database(tmp_path / "missing-weight.sqlite3")
    initialize_database(database)
    customer_id = _customer(database)
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('LEGACY', 'مخزون بدون وزن', 'finished_good', 'ماسورة', 10)
                """
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO inventory_moves(
                product_id, warehouse_id, quantity_in, unit_cost, reference_type
            ) VALUES (?, ?, 10, 100, 'opening')
            """,
            (product_id, warehouse_id),
        )
    repository = WeightInvoiceRepository(database)
    draft = repository.create_weight_sale_draft(
        customer_id=customer_id,
        lines=[{"product_id": product_id, "quantity": 2}],
        weight_mode="total_card",
        pricing_mode="uniform",
        net_weight_kg=20,
        uniform_price_per_kg=10,
    )

    with pytest.raises(ValueError, match="رصيد الوزن الفعلي"):
        repository.approve_weight_sale(draft["order_id"])

    assert float(
        database.fetch_one(
            "SELECT COALESCE(SUM(quantity_out), 0) AS value FROM inventory_moves "
            "WHERE product_id = ?",
            (product_id,),
        )["value"]
    ) == 0
    assert database.fetch_one(
        "SELECT id FROM sales_invoices WHERE sales_order_id = ?",
        (draft["order_id"],),
    ) is None
