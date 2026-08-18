from sqlalchemy import create_engine, inspect

from app.infrastructure.database.base import Base
from app.modules.identity import models as identity_models  # noqa: F401


def test_identity_metadata_creates_expected_tables() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    assert set(inspect(engine).get_table_names()) == {
        "audit_logs",
        "auth_sessions",
        "permissions",
        "role_permissions",
        "roles",
        "user_roles",
        "users",
    }


def test_identity_schema_has_unique_normalized_username() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    constraints = inspect(engine).get_unique_constraints("users")
    assert any(item["column_names"] == ["normalized_username"] for item in constraints)
