import os
import sys
from collections.abc import Generator
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ops.demo_seed import (  # noqa: E402
    seed_accounts,
    seed_crm,
    seed_inventory,
    seed_manufacturing,
    seed_master_data,
    seed_purchase,
    seed_return,
    seed_sales,
    seed_treasury,
)

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.master_data.models import CompanySettings, DocumentSequence  # noqa: E402


class TestApi:
    __test__ = False

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def login(self) -> None:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "Admin-password-2026"},
        )
        assert response.status_code == 200, response.text

    def get(self, path: str) -> Any:
        response = self.client.get("/api/v1" + path)
        assert response.status_code == 200, response.text
        return response.json()

    def post(self, path: str, payload: dict[str, Any], key: str | None = None) -> Any:
        csrf = self.client.cookies.get("pipeerp_csrf")
        assert csrf is not None
        headers = {"X-CSRF-Token": csrf}
        if key:
            headers["Idempotency-Key"] = key
        response = self.client.post("/api/v1" + path, json=payload, headers=headers)
        assert response.status_code in {200, 201}, response.text
        return response.json()


def _database() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _client(factory: sessionmaker[Session]) -> TestClient:
    def database_session() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_database_session] = database_session
    return TestClient(app)


def _seed_system(factory: sessionmaker[Session]) -> None:
    sequences = (
        ("purchase_order", "PO-"),
        ("purchase_receipt", "PR-"),
        ("purchase_invoice", "PI-"),
        ("sales_order", "SO-"),
        ("weight_card", "WC-"),
        ("sales_delivery", "SD-"),
        ("sales_invoice", "SI-"),
        ("sales_quotation", "QT-"),
        ("manufacturing_order", "MO-"),
        ("crm_lead", "LD-"),
        ("sales_return", "SR-"),
        ("customer_receipt", "CR-"),
        ("supplier_payment", "SP-"),
        ("financial_transfer", "TR-"),
        ("opening_balance", "OB-"),
        ("customer_adjustment", "CA-"),
    )
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password="Admin-password-2026",
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        db.add(
            CompanySettings(
                id=1,
                company_name_ar="PipeERP",
                currency_code="EGP",
                currency_decimal_places=2,
                tax_enabled=False,
                default_tax_rate=0,
                version=1,
            )
        )
        db.add_all(
            [
                DocumentSequence(
                    document_type=document_type,
                    prefix=prefix,
                    next_value=1,
                    padding=6,
                    version=1,
                )
                for document_type, prefix in sequences
            ]
        )


def _run_seed(api: TestApi) -> None:
    data = seed_master_data(api)  # type: ignore[arg-type]
    accounts = seed_accounts(api)  # type: ignore[arg-type]
    seed_inventory(api, data)  # type: ignore[arg-type]
    purchase = seed_purchase(api, data)  # type: ignore[arg-type]
    sale = seed_sales(api, data)  # type: ignore[arg-type]
    seed_manufacturing(api, data)  # type: ignore[arg-type]
    seed_crm(api)  # type: ignore[arg-type]
    seed_return(api, sale)  # type: ignore[arg-type]
    seed_treasury(api, data, accounts, purchase, sale)  # type: ignore[arg-type]


def test_demo_seed_builds_full_dataset_and_is_repeatable() -> None:
    factory = _database()
    _seed_system(factory)
    with _client(factory) as client:
        api = TestApi(client)
        api.login()
        _run_seed(api)
        first_summary = api.get("/dashboard/summary")
        _run_seed(api)
        second_summary = api.get("/dashboard/summary")

        assert first_summary == second_summary
        assert set(first_summary) == {
            "sales_today",
            "open_manufacturing_orders",
            "low_stock_products",
            "weight_sold_today_kg",
            "activity",
        }
        assert first_summary["activity"]
        assert len(api.get("/inventory/lot-balances")) >= 4
        crm_leads = api.get("/crm/leads")
        assert len(crm_leads) == 3
        assert sum("[PIPEERP-DEMO-V1]" in row["general_notes"] for row in crm_leads) == 1
        assert len(api.get("/returns/documents")) == 1
        assert len(api.get("/manufacturing/orders")) == 1
    app.dependency_overrides.clear()
