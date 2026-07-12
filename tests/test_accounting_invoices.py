import pytest

from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.accounting_repository import AccountingRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.print_settings_repository import PrintSettingsRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.repositories.sales_repository import SalesRepository
from app.services.receipt_template_service import build_sales_receipt_html


@pytest.fixture
def accounting_data(tmp_path) -> tuple[Database, dict[str, int]]:
    database = Database(tmp_path / "accounting.sqlite3")
    initialize_database(database)
    with database.session() as connection:
        supplier_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('supplier', 'مورد اختبار')"
            ).lastrowid
        )
        customer_id = int(
            connection.execute(
                "INSERT INTO partners(partner_type, name) VALUES ('customer', 'عميل اختبار')"
            ).lastrowid
        )
        raw_id = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('RAW-ACC', 'خامة اختبار', 'raw_material', 'كجم')
                """
            ).lastrowid
        )
        finished_id = int(
            connection.execute(
                """
                INSERT INTO products(code, name, product_type, unit)
                VALUES ('FIN-ACC', 'ماسورة اختبار', 'finished_good', 'قطعة')
                """
            ).lastrowid
        )
    InventoryRepository(database).post_adjustment(
        finished_id,
        10,
        unit_cost=25,
        lot_number="FG-ACC",
    )
    return database, {
        "supplier": supplier_id,
        "customer": customer_id,
        "raw": raw_id,
        "finished": finished_id,
    }


def test_draft_orders_are_advances_not_partner_debt(accounting_data) -> None:
    database, data = accounting_data
    purchase_id = PurchaseRepository(database).create_order_with_lines(
        supplier_id=data["supplier"],
        paid_amount=20,
        lines=[
            {
                "product_id": data["raw"],
                "lot_number": "RAW-LOT",
                "quantity": 5,
                "unit": "كجم",
                "unit_price": 10,
            }
        ],
    )
    sales_id = SalesRepository(database).create_order_with_lines(
        customer_id=data["customer"],
        paid_amount=10,
        lines=[
            {
                "product_id": data["finished"],
                "quantity": 2,
                "unit": "قطعة",
                "unit_price": 50,
            }
        ],
    )

    accounting = AccountingRepository(database)
    summary = accounting.dashboard_summary()
    assert summary["sales_total"] == 0
    assert summary["purchases_total"] == 0
    assert summary["receivables"] == 0
    assert summary["payables"] == 0
    assert summary["customer_advances"] == 10
    assert summary["supplier_advances"] == 20

    customer = accounting.list_partner_balances("customer")[0]
    supplier = accounting.list_partner_balances("supplier")[0]
    assert customer["invoices_total"] == 0
    assert customer["paid"] == 0
    assert customer["advances"] == 10
    assert customer["balance"] == 0
    assert supplier["invoices_total"] == 0
    assert supplier["paid"] == 0
    assert supplier["advances"] == 20
    assert supplier["balance"] == 0
    assert database.fetch_one("SELECT status FROM sales_orders WHERE id = ?", (sales_id,))
    assert database.fetch_one(
        "SELECT status FROM purchase_orders WHERE id = ?", (purchase_id,)
    )


def test_fulfillment_creates_debt_and_applies_order_advances(accounting_data) -> None:
    database, data = accounting_data
    purchase_repository = PurchaseRepository(database)
    sales_repository = SalesRepository(database)
    purchase_id = purchase_repository.create_order_with_lines(
        supplier_id=data["supplier"],
        paid_amount=20,
        lines=[
            {
                "product_id": data["raw"],
                "lot_number": "RAW-RECEIVED",
                "quantity": 5,
                "unit": "كجم",
                "unit_price": 10,
            }
        ],
    )
    sales_id = sales_repository.create_order_with_lines(
        customer_id=data["customer"],
        paid_amount=10,
        lines=[
            {
                "product_id": data["finished"],
                "quantity": 2,
                "unit": "قطعة",
                "unit_price": 50,
            }
        ],
    )
    purchase_repository.receive_order(purchase_id)
    sales_repository.deliver_order(sales_id)
    InvoiceRepository(database)._ensure_invoices()

    accounting = AccountingRepository(database)
    summary = accounting.dashboard_summary()
    assert summary["sales_total"] == 100
    assert summary["purchases_total"] == 50
    assert summary["receivables"] == 90
    assert summary["payables"] == 30
    assert summary["customer_advances"] == 0
    assert summary["supplier_advances"] == 0

    payment_id = accounting.record_payment(
        transaction_type="customer_receipt",
        partner_id=data["customer"],
        amount=30,
        payment_method="تحويل بنكي",
        reference_id=sales_id,
    )
    payment = database.fetch_one(
        "SELECT sales_invoice_id FROM payment_transactions WHERE id = ?",
        (payment_id,),
    )
    assert payment is not None and payment["sales_invoice_id"] is not None
    customer = accounting.list_partner_balances("customer")[0]
    assert customer["paid"] == 40
    assert customer["balance"] == 60


def test_print_defaults_and_receipt_template(accounting_data) -> None:
    database, _ = accounting_data
    settings = PrintSettingsRepository(database).get_settings()
    assert settings["company_name"] == "ثري إيه بايب - 3A Pipes"
    assert settings["paper_width_mm"] == "80"
    assert settings["instapay_handle"] == "ahmed.a351054@instapay"
    assert settings["logo_path"].endswith("default_logo.png")
    assert settings["qr_path"].endswith("default_instapay_qr.png")

    html = build_sales_receipt_html(
        {
            "invoice_number": "SI00001",
            "order_number": "SO00001",
            "invoice_date": "2026-07-12 01:00:00",
            "customer_name": "عميل <اختبار>",
            "customer_phone": "01000000000",
            "total": 100,
            "paid": 25,
            "remaining": 75,
            "payment_methods": "تحويل بنكي",
            "lines": [
                {
                    "code": "P-1",
                    "name": "ماسورة A1",
                    "quantity": 2,
                    "unit": "قطعة",
                    "unit_price": 50,
                    "line_total": 100,
                }
            ],
        },
        settings,
        logo_url="receipt:logo",
        qr_url="receipt:qr",
    )
    assert "ثري إيه بايب" in html
    assert "3A PIPES" in html
    assert "ahmed.a351054@instapay" in html
    assert "عميل &lt;اختبار&gt;" in html
    assert "75.00" in html
    assert 'class="logo" width="112"' in html
    assert 'class="qr" width="116"' in html
    assert 'class="company-en" dir="ltr"' in html
    assert 'class="product-head">الصنف' in html
    assert 'class="number-cell line-total" dir="ltr"' in html
    assert "class=\"remaining\"" in html
