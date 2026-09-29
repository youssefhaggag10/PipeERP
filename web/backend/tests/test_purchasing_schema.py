from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.master_data import models as master_data_models  # noqa: F401
from app.modules.purchasing import models as purchasing_models  # noqa: F401


def test_purchasing_metadata_contains_orders_receipts_and_supplier_invoices() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    inspector = inspect(engine)

    assert {
        "purchase_orders",
        "purchase_order_lines",
        "purchase_receipts",
        "purchase_receipt_lines",
        "supplier_invoices",
    } <= set(inspector.get_table_names())
    receipt_uniques = inspector.get_unique_constraints("purchase_receipts")
    assert any(item["column_names"] == ["idempotency_key"] for item in receipt_uniques)
