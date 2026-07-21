import os
import secrets
from datetime import date
from pathlib import Path

import pytest

if os.environ.get("PIPEERP_GUI_SMOKE") != "1":
    pytest.skip(
        "Acceptance artifacts run in the dedicated offscreen workflow",
        allow_module_level=True,
    )


def _seed_customer_and_product(database) -> tuple[int, int]:
    with database.session(immediate=True) as connection:
        warehouse_id = int(
            connection.execute(
                "SELECT id FROM warehouses WHERE code = 'MAIN'"
            ).fetchone()[0]
        )
        customer_id = int(
            connection.execute(
                """
                INSERT INTO partners(
                    partner_type, code, name, phone, address, opening_balance
                ) VALUES (
                    'customer', 'C-3A-001', 'شركة النور للمقاولات',
                    '01000000000', 'القاهرة', 500
                )
                """
            ).lastrowid
        )
        product_id = int(
            connection.execute(
                """
                INSERT INTO products(
                    code, name, product_type, unit, standard_weight_kg
                ) VALUES (
                    '20001', 'ماسورة UPVC 90 مم ضغط 6 بار طول 6 متر',
                    'finished_good', 'ماسورة', 28
                )
                """
            ).lastrowid
        )
        move_id = int(
            connection.execute(
                """
                INSERT INTO inventory_moves(
                    product_id, warehouse_id, quantity_in, quantity_out,
                    unit_cost, reference_type, notes
                ) VALUES (?, ?, 100, 0, 280, 'manufacturing', 'رصيد قبول')
                """,
                (product_id, warehouse_id),
            ).lastrowid
        )
        connection.execute(
            """
            INSERT INTO finished_good_weight_layers(
                product_id, warehouse_id, source_move_id,
                quantity_in, weight_in_kg, unit_cost_per_kg
            ) VALUES (?, ?, ?, 100, 2800, 10)
            """,
            (product_id, warehouse_id, move_id),
        )
        return customer_id, product_id


def test_weight_invoice_and_customer_statement_generate_real_artifacts(
    tmp_path: Path,
) -> None:
    from PySide6.QtCore import QDate
    from PySide6.QtWidgets import QApplication, QTabWidget

    from app.database.connection import Database
    from app.database.schema import initialize_database
    from app.repositories.customer_statement_accounting_repository import (
        CustomerStatementAccountingRepository,
    )
    from app.repositories.print_settings_repository import PrintSettingsRepository
    from app.repositories.standalone_weight_sales_repository import (
        StandaloneWeightSalesRepository,
    )
    from app.services.a4_print_service import A4PrintService
    from app.services.auth_service import AuthService
    from app.services.first_run_service import FirstRunService
    from app.ui.appearance import (
        AppearanceSettings,
        AppearanceSettingsRepository,
        apply_appearance,
    )
    from app.ui.customer_statement_page import CustomerStatementPage
    from app.ui.main_window import MainWindow
    from app.ui.weight_card_sales_page import WeightCardSalesPage

    database = Database(tmp_path / "acceptance.sqlite3")
    initialize_database(database)
    username = f"acceptance_{secrets.token_hex(8)}"
    password = secrets.token_urlsafe(32)
    FirstRunService(database).create_initial_admin(
        username=username,
        full_name="Acceptance Admin",
        password=password,
    )
    user = AuthService(database).authenticate(username, password)
    assert user is not None
    customer_id, product_id = _seed_customer_and_product(database)

    weight_repository = StandaloneWeightSalesRepository(database)
    draft = weight_repository.create_weight_sale_draft(
        customer_id=customer_id,
        lines=[
            {
                "product_id": product_id,
                "quantity": 10,
                "notes": "توريد للموقع الرئيسي",
            }
        ],
        weight_mode="total_card",
        pricing_mode="uniform",
        net_weight_kg=275,
        uniform_price_per_kg=20,
        vehicle_number="س ص ع 1234",
        discount_amount=100,
        transport_amount=250,
        tax_amount=0,
        sale_date="2026-01-10 10:30:00",
        notes="وزن فعلي طبقًا لكارتة الميزان",
    )
    approved = weight_repository.approve_weight_sale(int(draft["order_id"]))
    assert approved["invoice_number"].startswith("SI")

    accounting_repository = CustomerStatementAccountingRepository(database)
    transaction_id = accounting_repository.record_customer_receipt_allocated(
        customer_id=customer_id,
        amount=2000,
        payment_method="نقدي",
        financial_account_id=accounting_repository.get_default_financial_account_id(),
        allocations=[
            {
                "sales_invoice_id": int(approved["invoice_id"]),
                "amount": 2000,
            }
        ],
        notes="تحصيل مخصص لفاتورة الوزن",
    )
    with database.session(immediate=True) as connection:
        connection.execute(
            """
            UPDATE payment_transactions
            SET transaction_date = '2026-01-15 12:00:00'
            WHERE id = ?
            """,
            (transaction_id,),
        )

    statement = accounting_repository.get_customer_statement(
        customer_id=customer_id,
        date_from=date(2026, 1, 1),
        date_to=date(2026, 1, 31),
        detailed=True,
    )
    assert statement["summary"]["weight_sales_total"] == pytest.approx(5650)
    assert statement["summary"]["receipts_total"] == pytest.approx(2000)
    weight_movement = next(
        movement
        for movement in statement["movements"]
        if movement["document_type"] == "فاتورة بيع بالوزن"
    )
    assert len(weight_movement["lines"]) == 1

    app = QApplication.instance() or QApplication([])
    appearance = AppearanceSettingsRepository(database)
    appearance.save_settings(
        AppearanceSettings(theme="dark", font_size=12, scale_percent=90)
    )
    apply_appearance(app, appearance)
    window = MainWindow(user, database)
    window.resize(1600, 900)
    window.show()
    app.processEvents()

    weight_page = window.pages.widget(window.page_indexes["بيع بالوزن / الكارتة"])
    assert isinstance(weight_page, WeightCardSalesPage)
    window.pages_changed(window.page_indexes["بيع بالوزن / الكارتة"])
    weight_page.tabs.setCurrentIndex(0)
    customer_index = weight_page.customer_input.findData(customer_id)
    product_index = weight_page.product_input.findData(product_id)
    assert customer_index >= 0 and product_index >= 0
    weight_page.customer_input.setCurrentIndex(customer_index)
    weight_page.product_input.setCurrentIndex(product_index)
    weight_page.quantity_input.setValue(10)
    weight_page.add_line()
    weight_page.vehicle_input.setText("س ص ع 1234")
    weight_page.net_weight_input.setValue(275)
    weight_page.uniform_price_input.setValue(20)
    weight_page.discount_input.setValue(100)
    weight_page.transport_input.setValue(250)
    weight_page.notes_input.setPlainText("فاتورة وزن مستقلة — نموذج قبول")
    weight_page.refresh_totals()
    app.processEvents()

    artifact_dir = Path(".pipeerp-acceptance-artifacts")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    weight_screen = artifact_dir / "weight-invoice-screen.png"
    assert window.grab().save(str(weight_screen))
    assert weight_screen.stat().st_size > 10_000

    accounts_page = window.pages.widget(window.page_indexes["الحسابات"])
    window.pages_changed(window.page_indexes["الحسابات"])
    statement_page = accounts_page.findChild(CustomerStatementPage)
    assert statement_page is not None
    tabs = next(
        tab
        for tab in accounts_page.findChildren(QTabWidget)
        if any(tab.tabText(index).strip() == "كشف حساب العميل" for index in range(tab.count()))
    )
    statement_index = next(
        index
        for index in range(tabs.count())
        if tabs.tabText(index).strip() == "كشف حساب العميل"
    )
    tabs.setCurrentIndex(statement_index)
    customer_index = statement_page.customer_input.findData(customer_id)
    assert customer_index >= 0
    statement_page.customer_input.setCurrentIndex(customer_index)
    statement_page.date_from_input.setDate(QDate(2026, 1, 1))
    statement_page.date_to_input.setDate(QDate(2026, 1, 31))
    statement_page.statement_type_input.setCurrentIndex(1)
    statement_page.show_statement()
    app.processEvents()
    assert statement_page.statement_table.topLevelItemCount() >= 2
    statement_screen = artifact_dir / "customer-statement-screen.png"
    assert window.grab().save(str(statement_screen))
    assert statement_screen.stat().st_size > 10_000

    print_service = A4PrintService()
    settings = PrintSettingsRepository(database).get_settings()
    invoice_document = weight_repository.get_weight_invoice_print_data(
        int(approved["invoice_id"])
    )
    weight_pdf = print_service.export_weight_invoice_pdf(
        invoice_document,
        settings,
        artifact_dir / "weight-invoice-sample.pdf",
    )
    statement_pdf = print_service.export_customer_statement_pdf(
        statement,
        settings,
        artifact_dir / "customer-statement-sample.pdf",
    )
    statement_excel = CustomerStatementPage._write_excel(
        statement,
        artifact_dir / "customer-statement-sample.xlsx",
    )
    assert weight_pdf.stat().st_size > 10_000
    assert statement_pdf.stat().st_size > 10_000
    assert statement_excel.stat().st_size > 1_000
    weight_pages = print_service.render_weight_invoice_images(invoice_document, settings)
    statement_pages = print_service.render_customer_statement_images(statement, settings)
    assert len(weight_pages) == 1
    assert len(statement_pages) == 2
    assert "سعر الكيلو" not in {
        label for _, _, label, _ in print_service.weight_renderer.ITEM_COLUMNS
    }
    assert "وزن الكارتة" in {
        label for _, _, label, _ in print_service.weight_renderer.ITEM_COLUMNS
    }

    window.close()
    app.processEvents()
