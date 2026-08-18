from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.master_data import models as master_data_models  # noqa: F401


def test_master_data_metadata_contains_normalized_reference_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    tables = set(inspect(engine).get_table_names())

    assert {
        "company_settings",
        "document_sequences",
        "partners",
        "product_categories",
        "products",
        "units_of_measure",
        "warehouses",
    } <= tables


def test_product_and_partner_codes_are_unique_after_normalization() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    product_constraints = inspect(engine).get_unique_constraints("products")
    partner_constraints = inspect(engine).get_unique_constraints("partners")

    assert any(item["column_names"] == ["normalized_code"] for item in product_constraints)
    assert any(item["column_names"] == ["normalized_code"] for item in partner_constraints)
