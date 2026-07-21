from pathlib import Path

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.standalone_weight_sales_repository import (
    StandaloneWeightSalesRepository,
)
from app.repositories.treasury_invoice_repository import TreasuryInvoiceRepository


def _database(tmp_path: Path) -> Database:
    database = Database(tmp_path / "standalone-weight-sale.sqlite3")
    initialize_database(database)
    return database


def _masters(database: Database) -> dict[str, int]:
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute(
                "SELECT id FROM warehouses WHERE code = 'MAIN'"
            ).fetchone()[0]
        )
        customer_id = int(
            connection.execute(
                """
                INSERT INTO partners(partner_type, code, name)
                VALUES ('customer', 'CW-01', 'عميل بيع الوزن')
                """
            ).lastrowid
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('FG-W', 'ماسورة وزن', 'finished_good', 'قطعة', 20)
                """
            ).lastrowid
        )
        source_move_id = int(
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, quantity_out,
                    unit_cost, reference_type, notes
                ) VALUES (?, ?, 100, 0, 50, 'test_stock', 'weight sale test')
                """,
                (product_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO finished_good_weight_layers(
                product_id, warehouse_id, source_move_id,
                quantity_in, weight_in_kg, unit_cost_per_kg
            ) VALUES (?, ?, ?, 100, 2000, 2.5)
            """,
            (product_id, warehouse_id, source_move_id),
        )
    return {
        "warehouse": warehouse_id,
        "customer": customer_id,
        "product": product_id,
    }


def test_standalone_weight_sale_creates_internal_order_without_existing_sale(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    masters = _masters(database)
    repository = StandaloneWeightSalesRepository(database)

    assert database.fetch_one("SELECT COUNT(*) AS n FROM sales_orders")["n"] == 0

    result = repository.create_weight_sale(
        customer_id=masters["customer"],
        lines=[
            {
                "product_id": masters["product"],
                "quantity": 10,
                "unit": "قطعة",
            }
        ],
        net_weight_kg=198,
        price_per_kg=12,
        vehicle_number="أ ب ج 123",
    )

    order = database.fetch_one(
        """
        SELECT status, billing_method, weight_card_total
        FROM sales_orders WHERE id = ?
        """,
        (result["order_id"],),
    )
    assert tuple(order) == ("draft", "weight", 2376)

    cards = repository.list_weight_sales()
    assert len(cards) == 1
    assert cards[0]["total_pieces"] == 10
    assert cards[0]["net_weight_kg"] == 198
    assert cards[0]["total_amount"] == 2376

    repository.deliver_weight_sale(result["order_id"])
    TreasuryInvoiceRepository(database)._ensure_invoices()

    delivered = database.fetch_one(
        "SELECT status FROM sales_orders WHERE id = ?",
        (result["order_id"],),
    )
    invoice = database.fetch_one(
        """
        SELECT status, total FROM sales_invoices
        WHERE sales_order_id = ?
        """,
        (result["order_id"],),
    )
    allocation = database.fetch_one(
        """
        SELECT quantity_pieces, weight_kg
        FROM sales_weight_inventory_allocations
        """
    )
    assert delivered["status"] == "delivered"
    assert tuple(invoice) == ("posted", 2376)
    assert tuple(allocation) == (10, 198)
