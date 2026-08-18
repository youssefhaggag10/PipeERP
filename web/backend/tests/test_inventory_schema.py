from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.master_data import models as master_data_models  # noqa: F401


def test_inventory_metadata_contains_ledger_fifo_and_balance_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert {
        "inventory_allocations",
        "inventory_balances",
        "inventory_layers",
        "inventory_lots",
        "inventory_transactions",
    } <= set(inspector.get_table_names())

    transaction_uniques = inspector.get_unique_constraints("inventory_transactions")
    assert any(item["column_names"] == ["idempotency_key"] for item in transaction_uniques)

    balance_pk = inspector.get_pk_constraint("inventory_balances")
    assert balance_pk["constrained_columns"] == ["product_id", "warehouse_id"]
