from pathlib import Path

from app.database.connection import Database
from app.database.migrations import run_migrations
from app.database.schema import initialize_database


def _columns(database: Database, table_name: str) -> set[str]:
    rows = database.fetch_all(f"PRAGMA table_info({table_name})")
    return {str(row["name"]) for row in rows}


def test_schema_v9_upgrades_to_v10_without_losing_invoice_or_payment(tmp_path: Path) -> None:
    database = Database(tmp_path / "legacy-v9.sqlite3")
    with database.session(immediate=True) as connection:
        run_migrations(connection)
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 9
        warehouse_id = int(
            connection.execute("SELECT id FROM warehouses WHERE code = 'MAIN'").fetchone()[0]
        )
        customer_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, code, name) VALUES ('customer', 'C1', 'عميل')"
            ).lastrowid
        )
        order_id = int(
            connection.execute(
                """
                INSERT INTO sales_orders(
                    order_number, customer_id, warehouse_id, status, billing_method
                ) VALUES ('SO00001', ?, ?, 'delivered', 'weight')
                """,
                (customer_id, warehouse_id),
            ).lastrowid
        )
        invoice_id = int(
            connection.execute(
                """
                INSERT INTO sales_invoices(
                    invoice_number, sales_order_id, customer_id, status, total
                ) VALUES ('SI00001', ?, ?, 'posted', 1250)
                """,
                (order_id, customer_id),
            ).lastrowid
        )
        transaction_id = int(
            connection.execute(
                """
                INSERT INTO payment_transactions(
                    transaction_number, transaction_type, partner_id, amount,
                    reference_type, reference_id, sales_invoice_id
                ) VALUES ('TX00001', 'customer_receipt', ?, 250, 'sale', ?, ?)
                """,
                (customer_id, order_id, invoice_id),
            ).lastrowid
        )

    initialize_database(database)

    with database.session() as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 10
        invoice = connection.execute(
            "SELECT invoice_type, net_total FROM sales_invoices WHERE id = ?",
            (invoice_id,),
        ).fetchone()
        assert invoice["invoice_type"] == "weight"
        assert float(invoice["net_total"]) == 1250
        allocation = connection.execute(
            """
            SELECT sales_invoice_id, amount
            FROM payment_allocations WHERE transaction_id = ?
            """,
            (transaction_id,),
        ).fetchone()
        assert int(allocation["sales_invoice_id"]) == invoice_id
        assert float(allocation["amount"]) == 250

    initialize_database(database)
    with database.session() as connection:
        assert int(connection.execute("PRAGMA user_version").fetchone()[0]) == 10
        assert int(
            connection.execute("SELECT COUNT(*) FROM payment_allocations").fetchone()[0]
        ) == 1


def test_schema_v10_exposes_weight_invoice_fields(tmp_path: Path) -> None:
    database = Database(tmp_path / "new.sqlite3")
    initialize_database(database)

    assert {
        "invoice_type",
        "discount_amount",
        "transport_amount",
        "tax_amount",
        "net_total",
    }.issubset(_columns(database, "sales_invoices"))
    assert {
        "sales_invoice_id",
        "weight_mode",
        "pricing_mode",
        "use_vehicle_scale",
    }.issubset(_columns(database, "sales_weight_cards"))
    assert {"actual_weight_kg", "price_per_kg", "notes"}.issubset(
        _columns(database, "sales_weight_card_lines")
    )
    tables = {
        str(row["name"])
        for row in database.fetch_all(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert "payment_allocations" in tables
    assert "customer_account_adjustments" in tables
