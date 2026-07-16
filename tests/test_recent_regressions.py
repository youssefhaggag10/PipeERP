import os
from pathlib import Path

import pytest

from app.core.paths import AppPaths
from app.database.connection import Database
from app.database.schema import initialize_database
from app.models.user import User
from app.repositories.admin_only_crm_repository import AdminOnlyCRMRepository
from app.repositories.strict_product_repository import StrictProductRepository
from app.services.recipe_scrap_cost_service import estimate_recipe_scrap_cost


def test_recipe_scrap_cost_uses_weighted_material_cost(tmp_path: Path) -> None:
    database = Database(tmp_path / "scrap-cost.sqlite3")
    initialize_database(database)
    with database.session() as connection:
        products = []
        for index, unit_cost in enumerate((28.0, 39.0, 35.0, 38.0), start=1):
            product_id = int(
                connection.execute(
                    """
                    INSERT INTO products(code, name, product_type, unit)
                    VALUES (?, ?, 'raw_material', 'كجم')
                    """,
                    (f"RAW-{index}", f"خامة {index}"),
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, unit_cost, reference_type
                ) VALUES (?, 1, 1000, ?, 'adjustment')
                """,
                (product_id, unit_cost),
            )
            products.append(product_id)

    components = [
        {"product_id": products[0], "quantity_per_batch": 150},
        {"product_id": products[1], "quantity_per_batch": 50},
        {"product_id": products[2], "quantity_per_batch": 50},
        {"product_id": products[3], "quantity_per_batch": 25},
    ]
    result = estimate_recipe_scrap_cost(database, components)

    assert result["total_weight"] == pytest.approx(275.0)
    assert result["total_cost"] == pytest.approx(8850.0)
    assert result["unit_cost"] == pytest.approx(32.1818181818)


def test_non_finished_product_weight_is_forced_to_zero(tmp_path: Path) -> None:
    database = Database(tmp_path / "products.sqlite3")
    initialize_database(database)
    repository = StrictProductRepository(database)

    product_id = repository.create_product(
        {
            "code": "RAW-LOCK",
            "name": "خامة لا تقبل وزن قطعة",
            "product_type": "raw_material",
            "unit": "كجم",
            "standard_weight_kg": 99.0,
        }
    )

    row = database.fetch_one(
        "SELECT standard_weight_kg FROM products WHERE id = ?",
        (product_id,),
    )
    assert row is not None
    assert float(row["standard_weight_kg"]) == 0.0


def test_crm_scheduling_is_admin_only(tmp_path: Path) -> None:
    database = Database(tmp_path / "crm.sqlite3")
    initialize_database(database)
    normal_user = User(id=1, username="user", full_name="User", role="user")
    repository = AdminOnlyCRMRepository(database, normal_user)

    with pytest.raises(ValueError, match="للأدمن فقط"):
        repository.schedule(
            lead_id=1,
            kind="call",
            subject="متابعة",
            notes="",
            due_local="2026-07-17T10:00:00",
            priority="normal",
            owner=1,
        )


def test_app_paths_respect_explicit_data_directory(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "custom-data"
    monkeypatch.setenv(AppPaths.DATA_OVERRIDE_ENV, str(target))
    monkeypatch.delenv(AppPaths.PORTABLE_MODE_ENV, raising=False)

    resolved = AppPaths.data_dir()

    assert resolved == target.resolve()
    assert resolved.is_dir()
    assert AppPaths.logs_dir() == resolved / "logs"
    assert AppPaths.backups_dir() == resolved / "backups"
