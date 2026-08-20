from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.master_data import models as master_data_models  # noqa: F401
from app.modules.purchasing import models as purchasing_models  # noqa: F401
from app.modules.sales import models as sales_models  # noqa: F401


def test_sales_metadata_contains_desktop_sales_workflows() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())
    assert {
        "sales_orders",
        "sales_order_lines",
        "sales_weight_cards",
        "sales_weight_card_lines",
        "sales_deliveries",
        "sales_delivery_lines",
        "customer_invoices",
        "sales_quotations",
        "sales_quotation_lines",
    } <= tables
    assert "unit" in {column["name"] for column in inspect(engine).get_columns("sales_order_lines")}
