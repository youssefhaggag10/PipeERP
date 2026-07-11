import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.repositories.sales_repository import SalesRepository


@pytest.fixture
def database(tmp_path) -> Database:
    database = Database(tmp_path / "pipeerp.sqlite3")
    initialize_database(database)
    return database


def create_master_data(database: Database) -> dict[str, int]:
    with database.session() as connection:
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()["id"]
        )
        supplier_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('supplier', 'المورد')"
            ).lastrowid
        )
        customer_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('customer', 'العميل')"
            ).lastrowid
        )
        raw_one = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RM-1', 'خامة بولي إيثيلين', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        raw_two = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RM-2', 'ماستر باتش', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        finished_one = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('FG-1', 'ماسورة 20 مم', 'finished_good', 'قطعة')
                """
            ).lastrowid
        )
        finished_two = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('FG-2', 'ماسورة 25 مم', 'finished_good', 'قطعة')
                """
            ).lastrowid
        )
    return {
        "warehouse": warehouse_id,
        "supplier": supplier_id,
        "customer": customer_id,
        "raw_one": raw_one,
        "raw_two": raw_two,
        "finished_one": finished_one,
        "finished_two": finished_two,
    }


def test_purchase_order_saves_and_receives_multiple_lines(database: Database) -> None:
    data = create_master_data(database)
    repository = PurchaseRepository(database)
    order_id = repository.create_order_with_lines(
        supplier_id=data["supplier"],
        warehouse_id=data["warehouse"],
        notes="توريد خامات يوليو",
        lines=[
            {
                "product_id": data["raw_one"],
                "lot_number": "HDPE-01",
                "quantity": 500,
                "unit": "كجم",
                "unit_price": 35,
            },
            {
                "product_id": data["raw_two"],
                "lot_number": "COLOR-01",
                "quantity": 20,
                "unit": "كجم",
                "unit_price": 100,
            },
        ],
    )

    orders = repository.list_orders()
    assert orders[0]["line_count"] == 2
    assert "خامة بولي إيثيلين" in orders[0]["product_summary"]
    assert "ماستر باتش" in orders[0]["product_summary"]
    assert orders[0]["total"] == 19500

    details = repository.get_order_details(order_id)
    assert details["notes"] == "توريد خامات يوليو"
    assert [line["lot_number"] for line in details["lines"]] == ["HDPE-01", "COLOR-01"]

    repository.receive_order(order_id)

    moves = database.fetch_all(
        """
        SELECT product_id, quantity_in, unit_cost
        FROM inventory_moves
        WHERE reference_type = 'purchase' AND reference_id = ?
        ORDER BY id
        """,
        (order_id,),
    )
    assert [(row["product_id"], row["quantity_in"], row["unit_cost"]) for row in moves] == [
        (data["raw_one"], 500, 35),
        (data["raw_two"], 20, 100),
    ]


def test_invalid_purchase_line_rolls_back_whole_order(database: Database) -> None:
    data = create_master_data(database)
    repository = PurchaseRepository(database)
    with pytest.raises(ValueError, match="البند رقم 2"):
        repository.create_order_with_lines(
            supplier_id=data["supplier"],
            warehouse_id=data["warehouse"],
            lines=[
                {
                    "product_id": data["raw_one"],
                    "lot_number": "OK-LOT",
                    "quantity": 10,
                    "unit": "كجم",
                    "unit_price": 5,
                },
                {
                    "product_id": data["raw_two"],
                    "lot_number": "",
                    "quantity": 5,
                    "unit": "كجم",
                    "unit_price": 10,
                },
            ],
        )
    count = database.fetch_one("SELECT COUNT(*) AS count FROM purchase_orders")
    assert count is not None and count["count"] == 0


def test_sales_order_delivers_multiple_products_atomically(database: Database) -> None:
    data = create_master_data(database)
    inventory = InventoryRepository(database)
    inventory.post_adjustment(data["finished_one"], 10, unit_cost=12, lot_number="FG20-01")
    inventory.post_adjustment(data["finished_two"], 8, unit_cost=18, lot_number="FG25-01")
    repository = SalesRepository(database)
    order_id = repository.create_order_with_lines(
        customer_id=data["customer"],
        warehouse_id=data["warehouse"],
        notes="طلب عميل متعدد الأصناف",
        lines=[
            {
                "product_id": data["finished_one"],
                "quantity": 4,
                "unit": "قطعة",
                "unit_price": 30,
            },
            {
                "product_id": data["finished_two"],
                "quantity": 3,
                "unit": "قطعة",
                "unit_price": 45,
            },
        ],
    )

    order = repository.list_orders()[0]
    assert order["line_count"] == 2
    assert "ماسورة 20 مم" in order["product_summary"]
    assert "ماسورة 25 مم" in order["product_summary"]
    assert order["total"] == 255

    repository.deliver_order(order_id)

    details = repository.get_order_details(order_id)
    assert details["status"] == "delivered"
    balances = {
        row["id"]: row["quantity"]
        for row in inventory.list_stock_on_hand()
        if row["id"] in (data["finished_one"], data["finished_two"])
    }
    assert balances == {data["finished_one"]: 6, data["finished_two"]: 5}


def test_sales_multi_line_failure_rolls_back_all_products(database: Database) -> None:
    data = create_master_data(database)
    inventory = InventoryRepository(database)
    inventory.post_adjustment(data["finished_one"], 10, unit_cost=12, lot_number="FG20-01")
    inventory.post_adjustment(data["finished_two"], 2, unit_cost=18, lot_number="FG25-01")
    repository = SalesRepository(database)
    order_id = repository.create_order_with_lines(
        customer_id=data["customer"],
        warehouse_id=data["warehouse"],
        lines=[
            {
                "product_id": data["finished_one"],
                "quantity": 4,
                "unit": "قطعة",
                "unit_price": 30,
            },
            {
                "product_id": data["finished_two"],
                "quantity": 3,
                "unit": "قطعة",
                "unit_price": 45,
            },
        ],
    )

    with pytest.raises(ValueError, match="الرصيد غير كافي"):
        repository.deliver_order(order_id)

    order = database.fetch_one("SELECT status FROM sales_orders WHERE id = ?", (order_id,))
    moves = database.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM inventory_moves
        WHERE reference_type = 'sale' AND reference_id = ?
        """,
        (order_id,),
    )
    assert order is not None and order["status"] == "draft"
    assert moves is not None and moves["count"] == 0
