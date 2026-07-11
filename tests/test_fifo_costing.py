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


def create_master_data(database: Database) -> tuple[int, int, int]:
    with database.session() as connection:
        supplier_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('supplier', 'مورد')"
            ).lastrowid
        )
        customer_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('customer', 'عميل')"
            ).lastrowid
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('FG-1', 'ماسورة اختبار', 'finished_good', 'قطعة')
                """
            ).lastrowid
        )
    return supplier_id, customer_id, product_id


def receive(
    repository: PurchaseRepository,
    supplier_id: int,
    product_id: int,
    lot_number: str,
    quantity: float,
    unit_cost: float,
) -> int:
    order_id = repository.create_order(
        supplier_id,
        product_id,
        lot_number,
        quantity,
        "قطعة",
        unit_cost,
    )
    repository.receive_order(order_id)
    return order_id


def test_sale_uses_fifo_lots_and_actual_cost(database: Database) -> None:
    supplier_id, customer_id, product_id = create_master_data(database)
    purchases = PurchaseRepository(database)
    sales = SalesRepository(database)
    inventory = InventoryRepository(database)

    receive(purchases, supplier_id, product_id, "LOT-A", 10, 5)
    receive(purchases, supplier_id, product_id, "LOT-B", 10, 8)

    sale_id = sales.create_order(customer_id, product_id, 12, "قطعة", 100)
    sales.deliver_order(sale_id)

    outbound = database.fetch_all(
        """
        SELECT m.quantity_out, m.unit_cost, l.lot_number
        FROM inventory_moves m
        LEFT JOIN lots l ON l.id = m.lot_id
        WHERE m.reference_type = 'sale' AND m.reference_id = ?
        ORDER BY m.id
        """,
        (sale_id,),
    )
    assert [(row["quantity_out"], row["unit_cost"], row["lot_number"]) for row in outbound] == [
        (10, 5, "LOT-A"),
        (2, 8, "LOT-B"),
    ]
    assert sum(row["quantity_out"] * row["unit_cost"] for row in outbound) == 66

    lot_balances = inventory.list_lot_balances()
    balances = {row["lot_number"]: row["quantity_remaining"] for row in lot_balances}
    assert balances == {"LOT-A": 0, "LOT-B": 8}
    assert inventory.total_inventory_value() == 64


def test_delivery_is_idempotent(database: Database) -> None:
    supplier_id, customer_id, product_id = create_master_data(database)
    purchases = PurchaseRepository(database)
    sales = SalesRepository(database)
    receive(purchases, supplier_id, product_id, "LOT-A", 10, 5)
    sale_id = sales.create_order(customer_id, product_id, 4, "قطعة", 20)

    sales.deliver_order(sale_id)
    sales.deliver_order(sale_id)

    row = database.fetch_one(
        """
        SELECT COUNT(*) AS move_count, SUM(quantity_out) AS issued
        FROM inventory_moves
        WHERE reference_type = 'sale' AND reference_id = ?
        """,
        (sale_id,),
    )
    assert row is not None
    assert row["move_count"] == 1
    assert row["issued"] == 4


def test_multi_line_oversell_rolls_back_everything(database: Database) -> None:
    supplier_id, customer_id, product_id = create_master_data(database)
    purchases = PurchaseRepository(database)
    sales = SalesRepository(database)
    receive(purchases, supplier_id, product_id, "LOT-A", 10, 5)
    sale_id = sales.create_order(customer_id, product_id, 6, "قطعة", 20)
    with database.session() as connection:
        connection.execute(
            """
            INSERT INTO sales_order_lines(
                sales_order_id, product_id, quantity, unit, unit_price, line_total
            )
            VALUES (?, ?, 6, 'قطعة', 20, 120)
            """,
            (sale_id, product_id),
        )

    with pytest.raises(ValueError, match="الرصيد غير كافي"):
        sales.deliver_order(sale_id)

    order = database.fetch_one("SELECT status FROM sales_orders WHERE id = ?", (sale_id,))
    outbound = database.fetch_one(
        """
        SELECT COUNT(*) AS count
        FROM inventory_moves
        WHERE reference_type = 'sale' AND reference_id = ?
        """,
        (sale_id,),
    )
    assert order is not None and order["status"] == "draft"
    assert outbound is not None and outbound["count"] == 0


def test_negative_adjustment_uses_fifo_and_prevents_negative_stock(
    database: Database,
) -> None:
    _, _, product_id = create_master_data(database)
    inventory = InventoryRepository(database)
    inventory.post_adjustment(
        product_id,
        5,
        "رصيد افتتاحي",
        unit_cost=4,
        lot_number="OPEN-1",
    )

    with pytest.raises(ValueError, match="الرصيد غير كافي"):
        inventory.post_adjustment(product_id, -6, "جرد")
    inventory.post_adjustment(product_id, -2, "جرد")

    stock = database.fetch_one(
        """
        SELECT SUM(quantity_in - quantity_out) AS quantity
        FROM inventory_moves
        WHERE product_id = ?
        """,
        (product_id,),
    )
    issue = database.fetch_one(
        """
        SELECT quantity_out, unit_cost
        FROM inventory_moves
        WHERE product_id = ? AND quantity_out > 0
        """,
        (product_id,),
    )
    assert stock is not None and stock["quantity"] == 3
    assert issue is not None
    assert issue["quantity_out"] == 2
    assert issue["unit_cost"] == 4
