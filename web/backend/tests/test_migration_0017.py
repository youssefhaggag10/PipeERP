from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa


def _migration_module():  # type: ignore[no-untyped-def]
    migration_path = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260912_0017_return_source_layers.py"
    )
    spec = spec_from_file_location("migration_0017", migration_path)
    assert spec is not None
    assert spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def _create_backfill_tables(connection: sa.Connection) -> None:
    connection.execute(
        sa.text(
            """
            CREATE TABLE inventory_transactions (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                warehouse_id TEXT NOT NULL,
                transaction_type TEXT NOT NULL,
                reference_type TEXT NOT NULL,
                reference_id TEXT,
                reference_line_id TEXT,
                reversal_of_id TEXT,
                posted_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE TABLE inventory_layers (
                id TEXT PRIMARY KEY,
                product_id TEXT NOT NULL,
                warehouse_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT,
                source_line_id TEXT,
                source_transaction_id TEXT,
                received_at DATETIME NOT NULL
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE TABLE purchase_receipts (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                posted_at DATETIME
            )
            """
        )
    )
    connection.execute(
        sa.text(
            """
            CREATE TABLE purchase_receipt_lines (
                id TEXT PRIMARY KEY,
                purchase_receipt_id TEXT NOT NULL,
                purchase_order_line_id TEXT NOT NULL,
                inventory_transaction_id TEXT NOT NULL
            )
            """
        )
    )


def _insert_receipt_case(
    connection: sa.Connection, *, layer_count: int
) -> tuple[str, list[str]]:
    receipt_id = uuid4().hex
    line_id = uuid4().hex
    transaction_id = uuid4().hex
    product_id = uuid4().hex
    warehouse_id = uuid4().hex
    connection.execute(
        sa.text(
            """
            INSERT INTO purchase_receipts (id, status, posted_at)
            VALUES (:id, 'posted', '2026-09-01 12:00:00')
            """
        ),
        {"id": receipt_id},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO inventory_transactions (
                id, product_id, warehouse_id, transaction_type, reference_type,
                reference_id, reference_line_id, reversal_of_id, posted_at
            ) VALUES (
                :id, :product_id, :warehouse_id, 'receipt', 'purchase_receipt',
                :receipt_id, :line_id, NULL, '2026-09-01 12:00:00'
            )
            """
        ),
        {
            "id": transaction_id,
            "product_id": product_id,
            "warehouse_id": warehouse_id,
            "receipt_id": receipt_id,
            "line_id": line_id,
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO purchase_receipt_lines (
                id, purchase_receipt_id, purchase_order_line_id, inventory_transaction_id
            ) VALUES (:id, :receipt_id, :line_id, :transaction_id)
            """
        ),
        {
            "id": uuid4().hex,
            "receipt_id": receipt_id,
            "line_id": line_id,
            "transaction_id": transaction_id,
        },
    )
    layer_ids = []
    for _ in range(layer_count):
        layer_id = uuid4().hex
        layer_ids.append(layer_id)
        connection.execute(
            sa.text(
                """
                INSERT INTO inventory_layers (
                    id, product_id, warehouse_id, source_type, source_id,
                    source_line_id, source_transaction_id, received_at
                ) VALUES (
                    :id, :product_id, :warehouse_id, 'purchase_receipt', :receipt_id,
                    :line_id, NULL, '2026-09-01 12:00:00'
                )
                """
            ),
            {
                "id": layer_id,
                "product_id": product_id,
                "warehouse_id": warehouse_id,
                "receipt_id": receipt_id,
                "line_id": line_id,
            },
        )
    return transaction_id, layer_ids


def test_migration_backfills_only_deterministic_purchase_receipt_provenance() -> None:
    migration = _migration_module()
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        _create_backfill_tables(connection)
        deterministic_transaction, deterministic_layers = _insert_receipt_case(
            connection, layer_count=1
        )
        _, ambiguous_layers = _insert_receipt_case(connection, layer_count=2)
        missing_transaction, _ = _insert_receipt_case(connection, layer_count=0)

        migration._backfill_deterministic_receipt_layers(connection)

        deterministic = connection.scalar(
            sa.text(
                "SELECT source_transaction_id FROM inventory_layers WHERE id = :id"
            ),
            {"id": deterministic_layers[0]},
        )
        ambiguous = connection.execute(
            sa.text(
                "SELECT source_transaction_id FROM inventory_layers WHERE id IN (:a, :b)"
            ),
            {"a": ambiguous_layers[0], "b": ambiguous_layers[1]},
        ).scalars().all()
        missing_was_guessed = connection.scalar(
            sa.text(
                "SELECT COUNT(*) FROM inventory_layers WHERE source_transaction_id = :id"
            ),
            {"id": missing_transaction},
        )

    assert deterministic == deterministic_transaction
    assert ambiguous == [None, None]
    assert missing_was_guessed == 0


def test_migration_declares_legacy_default_without_historical_revaluation() -> None:
    source = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "20260912_0017_return_source_layers.py"
    ).read_text(encoding="utf-8")
    assert 'server_default="legacy_aggregate"' in source
    assert "UPDATE invoice_returns SET valuation_method = 'legacy_aggregate'" in source
    assert "UPDATE invoice_return_lines SET inventory_cost" not in source
