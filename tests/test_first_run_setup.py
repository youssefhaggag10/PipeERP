from pathlib import Path

import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.services.auth_service import AuthService
from app.services.first_run_service import FirstRunService


def test_first_run_creates_only_one_administrator(tmp_path: Path) -> None:
    database = Database(tmp_path / "first-run.sqlite3")
    initialize_database(database)
    service = FirstRunService(database)

    assert service.requires_setup() is True

    service.create_initial_admin(
        username="factory_admin",
        full_name="Factory Administrator",
        password="Strong-Pass-123",
    )

    assert service.requires_setup() is False
    user = AuthService(database).authenticate("factory_admin", "Strong-Pass-123")
    assert user is not None
    assert user.role == "admin"

    with pytest.raises(ValueError, match="بالفعل"):
        service.create_initial_admin(
            username="second_admin",
            full_name="Second Administrator",
            password="Strong-Pass-456",
        )


def test_first_run_rejects_short_password(tmp_path: Path) -> None:
    database = Database(tmp_path / "short-password.sqlite3")
    initialize_database(database)
    service = FirstRunService(database)

    with pytest.raises(ValueError, match="8 أحرف"):
        service.create_initial_admin(
            username="admin",
            full_name="Administrator",
            password="short",
        )
