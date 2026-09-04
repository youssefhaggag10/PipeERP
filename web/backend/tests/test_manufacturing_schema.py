from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401
from app.modules.inventory import models as inventory_models  # noqa: F401
from app.modules.manufacturing import models as manufacturing_models  # noqa: F401
from app.modules.master_data import models as master_data_models  # noqa: F401


def test_manufacturing_schema_contains_full_completion_audit_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    tables = set(inspect(engine).get_table_names())

    assert {
        "manufacturing_recipes",
        "manufacturing_recipe_outputs",
        "manufacturing_recipe_components",
        "manufacturing_orders",
        "manufacturing_order_outputs",
        "manufacturing_order_materials",
        "manufacturing_material_issues",
        "manufacturing_completions",
        "manufacturing_completion_outputs",
        "manufacturing_mix_adjustments",
        "manufacturing_mix_adjustment_materials",
    }.issubset(tables)


def test_manufacturing_order_preserves_each_idempotent_transition() -> None:
    columns = {column.name for column in manufacturing_models.ManufacturingOrder.__table__.columns}

    assert {
        "create_idempotency_key",
        "start_idempotency_key",
        "completion_idempotency_key",
        "cancellation_idempotency_key",
        "version",
    }.issubset(columns)
