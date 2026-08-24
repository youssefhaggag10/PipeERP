from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa


def test_received_purchase_invoice_backfill_is_safe_and_idempotent() -> None:
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260824_0016_backfill_received_purchase_invoices.py"
    )
    spec = spec_from_file_location("migration_0016", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    order_id = uuid4().hex
    supplier_id = uuid4().hex
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                CREATE TABLE purchase_orders (
                    id TEXT PRIMARY KEY,
                    supplier_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total NUMERIC NOT NULL,
                    order_date DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE supplier_invoices (
                    id TEXT PRIMARY KEY,
                    invoice_number TEXT NOT NULL UNIQUE,
                    supplier_invoice_number TEXT NOT NULL,
                    purchase_order_id TEXT NOT NULL UNIQUE,
                    supplier_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    total NUMERIC NOT NULL,
                    posted_at DATETIME,
                    version INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO purchase_orders (id, supplier_id, status, total, order_date)
                VALUES (:id, :supplier_id, 'received', 125.50, '2026-08-24 12:00:00')
                """
            ),
            {"id": order_id, "supplier_id": supplier_id},
        )

        migration.op.get_bind = lambda: connection
        migration.upgrade()
        migration.upgrade()

        invoices = connection.execute(
            sa.text(
                """
                SELECT id, purchase_order_id, supplier_id, status, total
                FROM supplier_invoices
                """
            )
        ).mappings().all()

    assert len(invoices) == 1
    assert len(invoices[0]["id"]) == 32
    assert invoices[0]["purchase_order_id"] == order_id
    assert invoices[0]["supplier_id"] == supplier_id
    assert invoices[0]["status"] == "posted"
    assert float(invoices[0]["total"]) == 125.5
