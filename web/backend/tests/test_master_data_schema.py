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


def test_all_reference_codes_are_unique_after_normalization() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    inspector = inspect(engine)
    for table_name in (
        "products",
        "partners",
        "units_of_measure",
        "product_categories",
        "warehouses",
    ):
        constraints = inspector.get_unique_constraints(table_name)
        assert any(item["column_names"] == ["normalized_code"] for item in constraints)

    warehouse_indexes = inspector.get_indexes("warehouses")
    assert any(
        item["name"] == "uq_warehouses_single_default" and item["unique"]
        for item in warehouse_indexes
    )
