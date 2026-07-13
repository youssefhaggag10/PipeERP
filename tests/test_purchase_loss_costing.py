from pathlib import Path

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.purchase_repository import PurchaseRepository


def test_purchase_manufacturing_cost_and_loss_are_capitalized(tmp_path: Path) -> None:
    database = Database(tmp_path / "purchase-loss.sqlite3")
    initialize_database(database)
    with database.session() as connection:
        supplier = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('supplier', 'المورد')"
            ).lastrowid
        )
        product = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('PVC', 'خامة PVC', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
    repository = PurchaseRepository(database)
    order_id = repository.create_order_with_lines(
        supplier_id=supplier,
        lines=[
            {
                "product_id": product,
                "lot_number": "PVC-001",
                "quantity": 1000,
                "unit": "كجم",
                "unit_price": 30,
                "manufacturing_unit_cost": 4,
                "purchase_loss_quantity": 5,
            }
        ],
    )
    details = repository.get_order_details(order_id)
    line = details["lines"][0]
    assert line["line_total"] == 34_000
    assert line["net_quantity"] == 995
    assert line["inventory_unit_cost"] == 34_000 / 995

    repository.receive_order(order_id)
    move = database.fetch_one(
        """
        SELECT quantity_in, unit_cost FROM inventory_moves
        WHERE reference_type = 'purchase' AND reference_id = ?
        """,
        (order_id,),
    )
    assert move is not None
    assert move["quantity_in"] == 995
    assert move["unit_cost"] == 34_000 / 995
