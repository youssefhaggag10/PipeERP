import os
from collections.abc import Generator
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("SECRET_KEY", "test-key-" * 5)
os.environ.setdefault("APP_ENV", "test")

from app.infrastructure.database.base import Base  # noqa: E402
from app.infrastructure.database.session import get_database_session  # noqa: E402
from app.main import app  # noqa: E402
from app.modules.identity.models import User  # noqa: E402
from app.modules.identity.service import ClientContext, create_initial_admin  # noqa: E402
from app.modules.master_data.models import (  # noqa: E402
    DocumentSequence,
    Partner,
    Warehouse,
)
from app.modules.sales.models import CustomerInvoice, SalesOrder  # noqa: E402
from app.modules.treasury.models import (  # noqa: E402
    FinancialAccount,
    PaymentAllocation,
    PaymentTransaction,
)
from app.modules.treasury.service import (  # noqa: E402
    apply_order_advances_to_invoice,
    list_partner_balances,
)


def _database() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _client(factory: sessionmaker[Session]) -> TestClient:
    def override_database() -> Generator[Session, None, None]:
        with factory() as db:
            yield db

    app.dependency_overrides[get_database_session] = override_database
    return TestClient(app)


def _seed(factory: sessionmaker[Session]) -> dict[str, str]:
    with factory.begin() as db:
        create_initial_admin(
            db,
            username="admin",
            display_name="مدير النظام",
            password="Admin-password-2026",
            client=ClientContext("127.0.0.1", "test", "bootstrap"),
        )
        warehouse = Warehouse(
            code="MAIN",
            normalized_code="MAIN",
            name_ar="مخزن المصنع",
            is_default=True,
            is_active=True,
            version=1,
        )
        customer = Partner(
            code="CUS-TR",
            normalized_code="CUS-TR",
            name_ar="عميل الخزينة",
            phone="",
            address="",
            tax_number="",
            is_customer=True,
            is_supplier=False,
            is_active=True,
            version=1,
        )
        supplier = Partner(
            code="SUP-TR",
            normalized_code="SUP-TR",
            name_ar="مورد الخزينة",
            phone="",
            address="",
            tax_number="",
            is_customer=False,
            is_supplier=True,
            is_active=True,
            version=1,
        )
        cash = FinancialAccount(
            code="CASH-MAIN",
            normalized_code="CASH-MAIN",
            name_ar="الخزينة الرئيسية",
            account_type="cash",
            opening_balance=Decimal("1000"),
            is_default=True,
            is_active=True,
            notes="",
            version=1,
        )
        db.add_all([warehouse, customer, supplier, cash])
        db.flush()
        admin_id = db.scalar(select(User.id).where(User.normalized_username == "admin"))
        assert admin_id is not None
        first_order = SalesOrder(
            order_number="SO-TR-1",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            billing_method="piece",
            status="delivered",
            notes="",
            subtotal=Decimal("500"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("500"),
            version=1,
            created_by_id=admin_id,
        )
        second_order = SalesOrder(
            order_number="SO-TR-2",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            billing_method="piece",
            status="delivered",
            notes="",
            subtotal=Decimal("700"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("700"),
            version=1,
            created_by_id=admin_id,
        )
        draft_order = SalesOrder(
            order_number="SO-TR-ADV",
            customer_id=customer.id,
            warehouse_id=warehouse.id,
            billing_method="piece",
            status="draft",
            notes="",
            subtotal=Decimal("300"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("300"),
            version=1,
            created_by_id=admin_id,
        )
        db.add_all([first_order, second_order, draft_order])
        db.flush()
        first_invoice = CustomerInvoice(
            invoice_number="SI-TR-1",
            sales_order_id=first_order.id,
            customer_id=customer.id,
            invoice_type="standard",
            status="posted",
            subtotal=Decimal("500"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("500"),
            notes="",
            version=1,
        )
        second_invoice = CustomerInvoice(
            invoice_number="SI-TR-2",
            sales_order_id=second_order.id,
            customer_id=customer.id,
            invoice_type="standard",
            status="posted",
            subtotal=Decimal("700"),
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=Decimal("700"),
            notes="",
            version=1,
        )
        db.add_all([first_invoice, second_invoice])
        db.add_all(
            [
                DocumentSequence(
                    document_type=document_type,
                    prefix=prefix,
                    next_value=1,
                    padding=6,
                    version=1,
                )
                for document_type, prefix in (
                    ("customer_receipt", "CR-"),
                    ("supplier_payment", "SP-"),
                    ("financial_transfer", "TR-"),
                    ("financial_adjustment", "ADJ-FIN-"),
                    ("opening_balance", "OB-"),
                    ("opening_balance_reversal", "OBR-"),
                    ("customer_adjustment", "CA-"),
                )
            ]
        )
        db.flush()
        return {
            "customer": str(customer.id),
            "supplier": str(supplier.id),
            "cash": str(cash.id),
            "first_invoice": str(first_invoice.id),
            "second_invoice": str(second_invoice.id),
            "draft_order": str(draft_order.id),
        }


def _login(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "Admin-password-2026"},
    )
    assert response.status_code == 200, response.text


def _headers(client: TestClient, key: str | None = None) -> dict[str, str]:
    csrf = client.cookies.get("pipeerp_csrf")
    assert csrf is not None
    result = {"X-CSRF-Token": csrf}
    if key is not None:
        result["Idempotency-Key"] = key
    return result


def test_receipt_allocations_advances_reversal_and_opening_balance() -> None:
    factory = _database()
    seeded = _seed(factory)
    with _client(factory) as client:
        _login(client)
        invoices = client.get("/api/v1/accounts/invoices?invoice_type=sales")
        assert invoices.status_code == 200, invoices.text
        assert {row["invoice_number"] for row in invoices.json()} == {
            "SI-TR-1",
            "SI-TR-2",
        }
        assert all(row["invoice_status"] == "posted" for row in invoices.json())
        assert all(row["delivery_return_status"] == "مُسلَّمة" for row in invoices.json())
        assert all(row["payment_status"] == "unpaid" for row in invoices.json())
        assert all(row["payment_methods"] == [] for row in invoices.json())
        receipt = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "customer-receipt-0001"),
            json={
                "transaction_type": "customer_receipt",
                "partner_id": seeded["customer"],
                "financial_account_id": seeded["cash"],
                "amount": "600",
                "payment_method": "cash",
                "allocations": [
                    {"invoice_id": seeded["first_invoice"], "amount": "400"},
                    {"invoice_id": seeded["second_invoice"], "amount": "150"},
                ],
                "notes": "تحصيل موزع",
            },
        )
        assert receipt.status_code == 201, receipt.text
        assert receipt.json()["allocated_amount"] == "550.00"
        assert receipt.json()["unallocated_amount"] == "50.00"

        replay = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "customer-receipt-0001"),
            json={
                "transaction_type": "customer_receipt",
                "partner_id": seeded["customer"],
                "financial_account_id": seeded["cash"],
                "amount": "600",
                "payment_method": "cash",
                "allocations": [
                    {"invoice_id": seeded["first_invoice"], "amount": "400"},
                    {"invoice_id": seeded["second_invoice"], "amount": "150"},
                ],
                "notes": "تحصيل موزع",
            },
        )
        assert replay.status_code == 201
        assert replay.json()["id"] == receipt.json()["id"]

        excessive = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "customer-receipt-0002"),
            json={
                "transaction_type": "customer_receipt",
                "partner_id": seeded["customer"],
                "financial_account_id": seeded["cash"],
                "amount": "200",
                "payment_method": "cash",
                "allocations": [{"invoice_id": seeded["first_invoice"], "amount": "200"}],
            },
        )
        assert excessive.status_code == 409

        balances = client.get("/api/v1/accounts/partner-balances?partner_type=customer")
        assert balances.status_code == 200
        balance = balances.json()[0]
        assert balance["paid_total"] == "550.00"
        assert balance["advances"] == "50.00"
        assert balance["balance"] == "600.00"

        opening = client.post(
            "/api/v1/accounts/opening-balances",
            headers=_headers(client),
            json={
                "partner_id": seeded["customer"],
                "nature": "debit",
                "amount": "100",
                "entry_date": date(2026, 1, 1).isoformat(),
                "notes": "رصيد افتتاحي معتمد",
            },
        )
        assert opening.status_code == 201, opening.text
        balances = client.get("/api/v1/accounts/partner-balances?partner_type=customer").json()
        assert balances[0]["opening_balance"] == "100.00"
        assert balances[0]["balance"] == "700.00"

        options = client.get("/api/v1/accounts/options")
        assert options.status_code == 200
        assert {row["code"] for row in options.json()["partners"]} == {
            "CUS-TR",
            "SUP-TR",
        }

        customer_adjustment = client.post(
            "/api/v1/accounts/customer-adjustments",
            headers=_headers(client),
            json={
                "customer_id": seeded["customer"],
                "adjustment_type": "debit",
                "amount": "25",
                "notes": "فروق مراجعة حساب العميل",
            },
        )
        assert customer_adjustment.status_code == 405

        summary = client.get("/api/v1/accounts/summary")
        assert summary.status_code == 200
        assert summary.json()["financial_balance"] == "1600.00"
        assert summary.json()["customer_advances"] == "50.00"
        assert summary.json()["receivables"] == "700.00"

        statement = client.get(
            f"/api/v1/accounts/partners/{seeded['customer']}/statement",
            params={
                "date_from": "2020-01-01",
                "date_to": "2030-12-31",
                "partner_type": "customer",
            },
        )
        assert statement.status_code == 200, statement.text
        assert statement.json()["closing_balance"] == "700.00"
        assert {row["movement_type"] for row in statement.json()["lines"]} == {
            "رصيد افتتاحي",
            "فاتورة مبيعات",
            "تحصيل عميل",
        }

        reversed_opening = client.post(
            f"/api/v1/accounts/opening-balances/{opening.json()['id']}/reversal",
            headers=_headers(client),
            json={"reason": "تصحيح بداية التشغيل"},
        )
        assert reversed_opening.status_code == 200
        assert reversed_opening.json()["status"] == "reversal"

        reversed_receipt = client.post(
            f"/api/v1/accounts/payments/{receipt.json()['id']}/reversal",
            headers=_headers(client, "customer-reversal-0001"),
            json={"reason": "تصحيح التحصيل"},
        )
        assert reversed_receipt.status_code == 200, reversed_receipt.text
        assert reversed_receipt.json()["status"] == "reversed"
        open_invoices = client.get(
            "/api/v1/accounts/open-invoices",
            params={
                "transaction_type": "customer_receipt",
                "partner_id": seeded["customer"],
            },
        )
        assert open_invoices.status_code == 200
        remaining_by_invoice = {
            row["invoice_number"]: row["remaining"] for row in open_invoices.json()
        }
        assert remaining_by_invoice == {"SI-TR-1": "500.00", "SI-TR-2": "700.00"}
    app.dependency_overrides.clear()


def test_system_reset_requires_admin_password_and_preserves_master_data() -> None:
    factory = _database()
    _seed(factory)
    with _client(factory) as client:
        _login(client)
        rejected = client.post(
            "/api/v1/system/reset",
            headers=_headers(client),
            json={"password": "wrong-password", "confirmation": "تصفير النظام"},
        )
        assert rejected.status_code == 422

        reset = client.post(
            "/api/v1/system/reset",
            headers=_headers(client),
            json={
                "password": "Admin-password-2026",
                "confirmation": "تصفير النظام",
            },
        )
        assert reset.status_code == 204, reset.text

    with factory() as db:
        assert db.scalar(select(Partner).where(Partner.code == "CUS-TR")) is not None
        assert db.scalar(select(SalesOrder).where(SalesOrder.order_number == "SO-TR-1")) is None
    app.dependency_overrides.clear()


def test_order_advance_is_attached_when_invoice_is_posted() -> None:
    factory = _database()
    seeded = _seed(factory)
    with _client(factory) as client:
        _login(client)
        advance = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "sales-advance-0001"),
            json={
                "transaction_type": "customer_receipt",
                "partner_id": seeded["customer"],
                "financial_account_id": seeded["cash"],
                "amount": "100",
                "payment_method": "cash",
                "reference_type": "sale",
                "reference_id": seeded["draft_order"],
                "notes": "دفعة عند إنشاء الأمر",
            },
        )
        assert advance.status_code == 201, advance.text
        assert advance.json()["unallocated_amount"] == "100.00"

    with factory.begin() as db:
        order = db.get(SalesOrder, UUID(seeded["draft_order"]))
        assert order is not None
        order.status = "delivered"
        invoice = CustomerInvoice(
            invoice_number="SI-TR-ADV",
            sales_order_id=order.id,
            customer_id=order.customer_id,
            invoice_type="standard",
            status="posted",
            subtotal=order.subtotal,
            discount_amount=0,
            transport_amount=0,
            tax_amount=0,
            total=order.total,
            notes="",
            version=1,
        )
        db.add(invoice)
        db.flush()
        apply_order_advances_to_invoice(
            db,
            reference_type="sale",
            reference_id=order.id,
            invoice=invoice,
        )
        payment = db.scalar(
            select(PaymentTransaction).where(
                PaymentTransaction.idempotency_key == "sales-advance-0001"
            )
        )
        assert payment is not None
        assert payment.customer_invoice_id == invoice.id
        allocation = db.scalar(
            select(PaymentAllocation).where(PaymentAllocation.payment_transaction_id == payment.id)
        )
        assert allocation is not None
        assert allocation.amount == Decimal("100.00")
        balances = list_partner_balances(db, partner_type="customer")
        customer_balance = next(
            item for item in balances if str(item.partner_id) == seeded["customer"]
        )
        assert customer_balance.paid_total == Decimal("100.00")
        assert customer_balance.advances == Decimal("0.00")
        assert customer_balance.balance == Decimal("1400.00")
    app.dependency_overrides.clear()


def test_transfer_and_adjustment_are_atomic_and_reversible() -> None:
    factory = _database()
    seeded = _seed(factory)
    with _client(factory) as client:
        _login(client)
        bank = client.post(
            "/api/v1/accounts/financial-accounts",
            headers=_headers(client),
            json={
                "code": "BANK-1",
                "name_ar": "البنك الرئيسي",
                "account_type": "bank",
                "opening_balance": "0",
                "is_default": False,
                "notes": "",
            },
        )
        assert bank.status_code == 201, bank.text
        transfer = client.post(
            "/api/v1/accounts/transfers",
            headers=_headers(client, "financial-transfer-0001"),
            json={
                "from_account_id": seeded["cash"],
                "to_account_id": bank.json()["id"],
                "amount": "250",
                "notes": "إيداع بنكي",
            },
        )
        assert transfer.status_code == 201, transfer.text
        accounts = client.get("/api/v1/accounts/financial-accounts").json()
        by_code = {row["code"]: row for row in accounts}
        assert by_code["CASH-MAIN"]["current_balance"] == "750.00"
        assert by_code["BANK-1"]["current_balance"] == "250.00"

        adjustment = client.post(
            "/api/v1/accounts/financial-adjustments",
            headers=_headers(client, "financial-adjustment-0001"),
            json={
                "financial_account_id": bank.json()["id"],
                "target_balance": "260",
                "notes": "مطابقة كشف البنك",
            },
        )
        assert adjustment.status_code == 201, adjustment.text
        assert adjustment.json()["amount"] == "10.00"

        incompatible = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "invalid-account-method-0001"),
            json={
                "transaction_type": "customer_receipt",
                "partner_id": seeded["customer"],
                "financial_account_id": bank.json()["id"],
                "amount": "10",
                "payment_method": "cash",
            },
        )
        assert incompatible.status_code == 409

        undone = client.post(
            f"/api/v1/accounts/transfers/{transfer.json()['id']}/reversal",
            headers=_headers(client, "financial-transfer-reversal-0001"),
            json={"reason": "تحويل مسجل بالخطأ"},
        )
        assert undone.status_code == 200, undone.text
        accounts = client.get("/api/v1/accounts/financial-accounts").json()
        by_code = {row["code"]: row for row in accounts}
        assert by_code["CASH-MAIN"]["current_balance"] == "1000.00"
        assert by_code["BANK-1"]["current_balance"] == "10.00"

        reversed_adjustment = client.post(
            f"/api/v1/accounts/financial-adjustments/{adjustment.json()['id']}/reversal",
            headers=_headers(client, "financial-adjustment-reversal-0001"),
            json={"reason": "إلغاء المطابقة التجريبية"},
        )
        assert reversed_adjustment.status_code == 200
        accounts = client.get("/api/v1/accounts/financial-accounts").json()
        by_code = {row["code"]: row for row in accounts}
        assert by_code["BANK-1"]["current_balance"] == "0.00"

        supplier_allocation = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "supplier-allocation-disabled"),
            json={
                "transaction_type": "supplier_payment",
                "partner_id": seeded["supplier"],
                "financial_account_id": seeded["cash"],
                "amount": "100",
                "payment_method": "cash",
                "allocations": [{"invoice_id": str(uuid4()), "amount": "100"}],
            },
        )
        assert supplier_allocation.status_code == 422

        supplier_statement = client.get(
            f"/api/v1/accounts/partners/{seeded['supplier']}/statement",
            params={
                "date_from": "2020-01-01",
                "date_to": "2030-12-31",
                "partner_type": "supplier",
            },
        )
        assert supplier_statement.status_code == 422

        supplier_payment = client.post(
            "/api/v1/accounts/payments",
            headers=_headers(client, "supplier-payment-0001"),
            json={
                "transaction_type": "supplier_payment",
                "partner_id": seeded["supplier"],
                "financial_account_id": seeded["cash"],
                "amount": "2000",
                "payment_method": "cash",
                "notes": "سداد مقدم مسموح حتى مع رصيد خزينة سالب",
            },
        )
        assert supplier_payment.status_code == 201, supplier_payment.text
        accounts = client.get("/api/v1/accounts/financial-accounts").json()
        by_code = {row["code"]: row for row in accounts}
        assert by_code["CASH-MAIN"]["current_balance"] == "-1000.00"
    app.dependency_overrides.clear()


def test_accounts_read_role_can_view_but_cannot_post() -> None:
    factory = _database()
    _seed(factory)
    with _client(factory) as admin:
        _login(admin)
        created = admin.post(
            "/api/v1/identity/users",
            headers=_headers(admin),
            json={
                "username": "treasury-reader",
                "display_name": "مراجع الحسابات",
                "password": "Treasury-reader-password-2026",
                "role_codes": ["operations_manager"],
                "must_change_password": False,
            },
        )
        assert created.status_code == 201, created.text

        with _client(factory) as reader:
            response = reader.post(
                "/api/v1/auth/login",
                json={
                    "username": "treasury-reader",
                    "password": "Treasury-reader-password-2026",
                },
            )
            assert response.status_code == 200
            assert reader.get("/api/v1/accounts/options").status_code == 200
            denied = reader.post(
                "/api/v1/accounts/financial-accounts",
                headers=_headers(reader),
                json={
                    "code": "DENIED",
                    "name_ar": "حساب غير مسموح",
                    "account_type": "cash",
                    "opening_balance": "0",
                    "is_default": False,
                    "notes": "",
                },
            )
            assert denied.status_code == 403
    app.dependency_overrides.clear()
