from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.quotation_repository import QuotationRepository


def test_quotation_is_multi_line_and_has_no_operational_effects(tmp_path: Path) -> None:
    database = Database(tmp_path / "quotation.sqlite3")
    initialize_database(database)
    with database.session() as connection:
        customer_id = int(
            connection.execute(
                """
                INSERT INTO partners(partner_type, code, name, phone)
                VALUES ('customer', 'C001', 'Test Customer', '01000000000')
                """
            ).lastrowid
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('P001', 'Pipe 110 mm', 'finished', 'قطعة')
                """
            ).lastrowid
        )

    repository = QuotationRepository(database)
    quotation_id = repository.create_quotation(
        customer_id=customer_id,
        valid_until="2026-08-01",
        notes="Quotation only",
        lines=[
            {
                "product_id": product_id,
                "item_name": "Pipe 110 mm",
                "quantity": 10,
                "unit": "قطعة",
                "unit_price": 25.5,
                "notes": "",
            },
            {
                "product_id": None,
                "item_name": "Delivery service",
                "quantity": 1,
                "unit": "خدمة",
                "unit_price": 100,
                "notes": "Optional",
            },
        ],
    )

    data = repository.get_print_data(quotation_id)
    assert data["document_title"] == "عرض سعر"
    assert data["quotation_number"] == "QT00001"
    assert data["total"] == pytest.approx(355.0)
    assert len(data["lines"]) == 2

    assert database.fetch_one("SELECT COUNT(*) AS count FROM sales_orders")["count"] == 0
    assert database.fetch_one("SELECT COUNT(*) AS count FROM sales_invoices")["count"] == 0
    assert database.fetch_one("SELECT COUNT(*) AS count FROM inventory_moves")["count"] == 0
    assert database.fetch_one("SELECT COUNT(*) AS count FROM payment_transactions")["count"] == 0
