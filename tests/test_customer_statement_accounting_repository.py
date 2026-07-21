from datetime import date
from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.customer_statement_accounting_repository import (
    CustomerStatementAccountingRepository,
)


def _seed_customer_documents(database: Database) -> dict[str, int]:
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        customer_id = int(
            connection.execute(
                """
                INSERT INTO partners(
                    partner_type, code, name, opening_balance
                ) VALUES ('customer', 'C-ST', 'عميل كشف الحساب', 100)
                """
            ).lastrowid
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES ('PIPE', 'ماسورة اختبار', 'finished_good', 'ماسورة', 10)
                """
            ).lastrowid
        )

        standard_order_id = int(
            connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, order_date, status
                ) VALUES ('SO-STANDARD', ?, ?, '2026-01-05 10:00:00', 'delivered')
                """,
                (customer_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sales_order_lines(
                sales_order_id, product_id, quantity, unit, unit_price, line_total
            ) VALUES (?, ?, 10, 'ماسورة', 100, 1000)
            """,
            (standard_order_id, product_id),
        )
        standard_invoice_id = int(
            connection.execute(
                """
                INSERT INTO sales_invoices(
                    invoice_number, sales_order_id, customer_id, invoice_date,
                    status, total, invoice_type, net_total, posted_at
                ) VALUES ('SI-STANDARD', ?, ?, '2026-01-05 10:00:00',
                          'posted', 1000, 'standard', 1000, '2026-01-05 10:00:00')
                """,
                (standard_order_id, customer_id),
            ).lastrowid
        )

        weight_order_id = int(
            connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, order_date,
                    status, billing_method, weight_card_total,
                    weight_mode, weight_pricing_mode
                ) VALUES ('SO-WEIGHT', ?, ?, '2026-01-10 10:00:00',
                          'delivered', 'weight', 2000, 'total_card', 'uniform')
                """,
                (customer_id, warehouse_id),
            ).lastrowid
        )
        weight_order_line_id = int(
            connection.execute(
                """
                INSERT INTO sales_order_lines(
                    sales_order_id, product_id, quantity, unit, unit_price,
                    line_total, billing_weight_kg, price_per_kg
                ) VALUES (?, ?, 10, 'ماسورة', 200, 2000, 100, 20)
                """,
                (weight_order_id, product_id),
            ).lastrowid
        )
        weight_invoice_id = int(
            connection.execute(
                """
                INSERT INTO sales_invoices(
                    invoice_number, sales_order_id, customer_id, invoice_date,
                    status, total, invoice_type, net_total, posted_at
                ) VALUES ('SI-WEIGHT', ?, ?, '2026-01-10 10:00:00',
                          'posted', 2000, 'weight', 2000, '2026-01-10 10:00:00')
                """,
                (weight_order_id, customer_id),
            ).lastrowid
        )
        weight_card_id = int(
            connection.execute(
                """
                INSERT INTO sales_weight_cards(
                    sales_order_id, sales_invoice_id, card_number, card_date,
                    net_weight_kg, price_per_kg, total_amount, status,
                    weight_mode, pricing_mode, net_amount
                ) VALUES (?, ?, 'WC000001', '2026-01-10 10:00:00',
                          100, 20, 2000, 'posted', 'total_card', 'uniform', 2000)
                """,
                (weight_order_id, weight_invoice_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sales_weight_card_lines(
                weight_card_id, sales_order_line_id, product_id,
                quantity_pieces, standard_weight_kg, theoretical_weight_kg,
                allocated_weight_kg, actual_weight_kg, price_per_kg,
                line_total, notes
            ) VALUES (?, ?, ?, 10, 10, 100, 100, 100, 20, 2000, 'وزن فعلي')
            """,
            (weight_card_id, weight_order_line_id, product_id),
        )

        draft_order_id = int(
            connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, order_date,
                    status, billing_method
                ) VALUES ('SO-DRAFT', ?, ?, '2026-01-11 10:00:00', 'draft', 'weight')
                """,
                (customer_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO sales_order_lines(
                sales_order_id, product_id, quantity, unit, unit_price, line_total
            ) VALUES (?, ?, 1, 'ماسورة', 999, 999)
            """,
            (draft_order_id, product_id),
        )

        return_id = int(
            connection.execute(
                """
                INSERT INTO invoice_returns(
                    return_number, invoice_type, invoice_id, return_date,
                    total, reason
                ) VALUES ('SR000001', 'sales', ?, '2026-01-12 10:00:00',
                          200, 'مرتجع اختبار')
                """,
                (standard_invoice_id,),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO invoice_return_lines(
                return_id, order_line_id, product_id, quantity,
                unit, unit_price, line_total
            ) VALUES (?, (SELECT id FROM sales_order_lines WHERE sales_order_id = ?),
                      ?, 2, 'ماسورة', 100, 200)
            """,
            (return_id, standard_order_id, product_id),
        )
        connection.execute(
            """
            INSERT INTO customer_account_adjustments(
                adjustment_number, adjustment_date, customer_id,
                adjustment_type, amount, status, notes
            ) VALUES ('ADJ-C-000001', '2026-01-20 10:00:00', ?,
                      'credit', 50, 'posted', 'خصم مسموح')
            """,
            (customer_id,),
        )
        return {
            "customer_id": customer_id,
            "standard_invoice_id": standard_invoice_id,
            "weight_invoice_id": weight_invoice_id,
            "draft_order_id": draft_order_id,
        }


def test_receipt_can_be_allocated_to_multiple_invoices(tmp_path: Path) -> None:
    database = Database(tmp_path / "allocations.sqlite3")
    initialize_database(database)
    repository = CustomerStatementAccountingRepository(database)
    seeded = _seed_customer_documents(database)
    account_id = repository.get_default_financial_account_id()

    transaction_id = repository.record_customer_receipt_allocated(
        customer_id=seeded["customer_id"],
        amount=600,
        payment_method="نقدي",
        financial_account_id=account_id,
        allocations=[
            {"sales_invoice_id": seeded["standard_invoice_id"], "amount": 400},
            {"sales_invoice_id": seeded["weight_invoice_id"], "amount": 150},
        ],
        notes="تحصيل موزع",
    )

    allocations = database.fetch_all(
        """
        SELECT sales_invoice_id, amount FROM payment_allocations
        WHERE transaction_id = ? ORDER BY sales_invoice_id
        """,
        (transaction_id,),
    )
    assert [float(row["amount"]) for row in allocations] == pytest.approx([400, 150])
    transaction = database.fetch_one(
        "SELECT amount, reference_id, sales_invoice_id FROM payment_transactions WHERE id = ?",
        (transaction_id,),
    )
    assert float(transaction["amount"]) == pytest.approx(600)
    assert transaction["reference_id"] is None
    assert transaction["sales_invoice_id"] is None

    open_invoices = {
        int(row["id"]): row
        for row in repository.list_open_sales_invoices(seeded["customer_id"])
    }
    assert open_invoices[seeded["standard_invoice_id"]]["remaining"] == pytest.approx(400)
    assert open_invoices[seeded["weight_invoice_id"]]["remaining"] == pytest.approx(1850)


def test_customer_statement_running_balance_and_draft_exclusion(tmp_path: Path) -> None:
    database = Database(tmp_path / "statement.sqlite3")
    initialize_database(database)
    repository = CustomerStatementAccountingRepository(database)
    seeded = _seed_customer_documents(database)
    repository.record_customer_receipt_allocated(
        customer_id=seeded["customer_id"],
        amount=500,
        payment_method="نقدي",
        financial_account_id=repository.get_default_financial_account_id(),
        allocations=[
            {"sales_invoice_id": seeded["standard_invoice_id"], "amount": 500}
        ],
        notes="تحصيل يناير",
    )
    with database.session(immediate=True) as connection:
        connection.execute(
            "UPDATE payment_transactions SET transaction_date = '2026-01-15 10:00:00'"
        )

    statement = repository.get_customer_statement(
        customer_id=seeded["customer_id"],
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        include_drafts=False,
        detailed=False,
    )

    document_types = [row["document_type"] for row in statement["movements"]]
    assert "فاتورة بيع عادية" in document_types
    assert "فاتورة بيع بالوزن" in document_types
    assert "مرتجع مبيعات" in document_types
    assert "تحصيل عميل" in document_types
    assert "تسوية دائنة" in document_types
    assert not any("مسودة" in value for value in document_types)
    assert statement["summary"]["opening_balance"] == pytest.approx(100)
    assert statement["summary"]["standard_sales_total"] == pytest.approx(1000)
    assert statement["summary"]["weight_sales_total"] == pytest.approx(2000)
    assert statement["summary"]["returns_total"] == pytest.approx(200)
    assert statement["summary"]["receipts_total"] == pytest.approx(500)
    assert statement["summary"]["adjustments_total"] == pytest.approx(-50)
    assert statement["summary"]["closing_balance"] == pytest.approx(2350)
    assert statement["movements"][-1]["running_balance"] == pytest.approx(2350)

    review = repository.get_customer_statement(
        customer_id=seeded["customer_id"],
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        include_drafts=True,
        detailed=False,
    )
    draft = next(row for row in review["movements"] if "مسودة" in row["document_type"])
    assert draft["debit"] == 0
    assert draft["credit"] == 0
    assert review["summary"]["closing_balance"] == pytest.approx(2350)


def test_detailed_statement_contains_weight_invoice_lines(tmp_path: Path) -> None:
    database = Database(tmp_path / "details.sqlite3")
    initialize_database(database)
    repository = CustomerStatementAccountingRepository(database)
    seeded = _seed_customer_documents(database)

    statement = repository.get_customer_statement(
        customer_id=seeded["customer_id"],
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        detailed=True,
    )
    weight_invoice = next(
        row for row in statement["movements"] if row["document_type"] == "فاتورة بيع بالوزن"
    )
    assert len(weight_invoice["lines"]) == 1
    line = weight_invoice["lines"][0]
    assert float(line["quantity"]) == pytest.approx(10)
    assert float(line["actual_weight_kg"]) == pytest.approx(100)
    assert float(line["price_per_kg"]) == pytest.approx(20)
    assert float(line["line_total"]) == pytest.approx(2000)
    assert line["notes"] == "وزن فعلي"
