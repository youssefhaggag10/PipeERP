from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.master_data import models as master_data_models  # noqa: F401
from app.modules.purchasing import models as purchasing_models  # noqa: F401
from app.modules.returns import models as returns_models
from app.modules.sales import models as sales_models  # noqa: F401
from app.modules.treasury import models as treasury_models  # noqa: F401


def test_returns_schema_contains_documents_lines_and_refunds() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert {
        "invoice_returns",
        "invoice_return_lines",
        "return_refunds",
    }.issubset(set(inspect(engine).get_table_names()))


def test_returns_documents_preserve_idempotency_reversal_and_source_links() -> None:
    document_columns = {column.name for column in returns_models.InvoiceReturn.__table__.columns}
    line_columns = {column.name for column in returns_models.InvoiceReturnLine.__table__.columns}
    refund_columns = {column.name for column in returns_models.ReturnRefund.__table__.columns}

    assert {"idempotency_key", "reversal_idempotency_key", "version"}.issubset(
        document_columns
    )
    assert {
        "sales_order_line_id",
        "purchase_order_line_id",
        "inventory_transaction_id",
        "reversal_inventory_transaction_id",
        "cost_basis",
        "inventory_cost",
    }.issubset(line_columns)
    assert {
        "customer_invoice_id",
        "supplier_invoice_id",
        "financial_account_id",
        "idempotency_key",
        "reversal_idempotency_key",
        "version",
    }.issubset(refund_columns)
