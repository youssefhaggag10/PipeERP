import os
import secrets
from pathlib import Path

import pytest

if os.environ.get("PIPEERP_GUI_SMOKE") != "1":
    pytest.skip("GUI smoke tests run in the dedicated offscreen workflow", allow_module_level=True)


def test_offscreen_themes_and_core_windows_open_without_crash(tmp_path: Path) -> None:
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import (
        QApplication,
        QPushButton,
        QScrollArea,
        QTabWidget,
        QWidget,
    )

    from app.database.connection import Database
    from app.database.schema import initialize_database
    from app.services.auth_service import AuthService
    from app.services.first_run_service import FirstRunService
    from app.ui.appearance import (
        AppearanceSettings,
        AppearanceSettingsRepository,
        apply_appearance,
    )
    from app.ui.customer_statement_page import CustomerStatementPage
    from app.ui.main_window import MainWindow, SalesNavigationDelegate
    from app.ui.treasury_order_pages import TreasurySalesAccountingPageWithPrint
    from app.ui.weight_card_sales_page import WeightCardSalesPage

    database = Database(tmp_path / "gui-smoke.sqlite3")
    initialize_database(database)
    username = f"smoke_{secrets.token_hex(8)}"
    credential = secrets.token_urlsafe(32)
    FirstRunService(database).create_initial_admin(
        username=username,
        full_name="Smoke Admin",
        password=credential,
    )
    user = AuthService(database).authenticate(username, credential)
    assert user is not None

    app = QApplication.instance() or QApplication([])
    appearance = AppearanceSettingsRepository(database)
    for theme in ("dark", "light", "system"):
        expected = AppearanceSettings(theme=theme, font_size=14, scale_percent=110)
        appearance.save_settings(expected)
        assert apply_appearance(app, appearance) == expected
        assert app.styleSheet().strip()

    window = MainWindow(user, database)
    window.show()
    app.processEvents()

    expected_pages = {
        "الرئيسية",
        "CRM متابعة العملاء",
        "الأصناف",
        "رصيد المخزون",
        "المشتريات",
        "المبيعات",
        "بيع بالوزن / الكارتة",
        "الحسابات",
        "التصنيع",
        "الإعدادات",
    }
    assert expected_pages.issubset(window.page_indexes)
    for title in expected_pages:
        index = window.page_indexes[title]
        window.pages_changed(index)
        app.processEvents()
        assert window.pages.currentIndex() == index
        assert window.pages.widget(index) is not None

    sales_items = [
        window.navigation.item(row)
        for row in range(window.navigation.count())
        if window.navigation.item(row).text().strip() == "المبيعات"
    ]
    assert len(sales_items) == 1
    sales_item = sales_items[0]
    assert window.navigation.itemWidget(sales_item) is None
    assert window.navigation.uniformItemSizes()

    delegate = window.navigation.itemDelegate()
    assert isinstance(delegate, SalesNavigationDelegate)
    item_rect = window.navigation.visualItemRect(sales_item)
    arrow_rect = delegate.arrow_rect(item_rect)
    text_rect = delegate.text_rect(item_rect, window.navigation.fontMetrics().height())
    assert item_rect.contains(arrow_rect)
    assert item_rect.contains(text_rect)
    assert not arrow_rect.intersects(text_rect)
    assert arrow_rect.left() - item_rect.left() <= 22
    text_width = window.navigation.fontMetrics().horizontalAdvance("المبيعات")
    assert text_width <= text_rect.width()
    assert [action.text() for action in window.sales_weight_menu.actions()] == [
        "البيع بالوزن / الكارتة"
    ]

    window.navigation.setCurrentItem(sales_item)
    app.processEvents()
    assert window.pages.currentIndex() == window.page_indexes["المبيعات"]

    window.weight_sales_action.trigger()
    app.processEvents()
    assert window.navigation.currentItem() is sales_item
    assert window.pages.currentIndex() == window.page_indexes["بيع بالوزن / الكارتة"]

    normal_sales_page = window.pages.widget(window.page_indexes["المبيعات"])
    weight_sales_page = window.pages.widget(window.page_indexes["بيع بالوزن / الكارتة"])
    assert isinstance(normal_sales_page, TreasurySalesAccountingPageWithPrint)
    assert isinstance(weight_sales_page, QWidget)
    assert isinstance(weight_sales_page, WeightCardSalesPage)
    assert not isinstance(weight_sales_page, TreasurySalesAccountingPageWithPrint)
    assert weight_sales_page.order_number_input.isReadOnly()
    assert weight_sales_page.invoice_number_input.isReadOnly()
    assert weight_sales_page.card_number_input.isReadOnly()
    assert weight_sales_page.card_number_input.text().startswith("WC")
    assert not weight_sales_page.vehicle_scale_panel.isVisible()
    assert weight_sales_page.lines_table.isColumnHidden(0)
    assert weight_sales_page.lines_table.isColumnHidden(8)
    assert weight_sales_page.lines_table.isColumnHidden(9)
    assert {
        weight_sales_page.weight_mode_input.itemData(index)
        for index in range(weight_sales_page.weight_mode_input.count())
    } == {"total_card", "per_line"}
    assert {
        weight_sales_page.pricing_mode_input.itemData(index)
        for index in range(weight_sales_page.pricing_mode_input.count())
    } == {"uniform", "per_line"}
    weight_buttons = {
        button.text().strip() for button in weight_sales_page.findChildren(QPushButton)
    }
    assert {
        "حفظ كمسودة",
        "اعتماد الفاتورة",
        "اعتماد وطباعة",
        "تفريغ البيانات",
        "إلغاء",
    }.issubset(weight_buttons)

    purchase_page = window.pages.widget(window.page_indexes["المشتريات"])
    inventory_page = window.pages.widget(window.page_indexes["رصيد المخزون"])
    assert purchase_page.lot_input.isReadOnly()
    assert inventory_page.lot_input.isReadOnly()

    accounts_page = window.pages.widget(window.page_indexes["الحسابات"])
    tabs = next(
        tab
        for tab in accounts_page.findChildren(QTabWidget)
        if tab.count() and tab.tabText(0).strip() == "الملخص"
    )
    treasury_index = next(
        index
        for index in range(tabs.count())
        if tabs.tabText(index).strip() == "الخزينة والبنوك"
    )
    treasury_scroll = tabs.widget(treasury_index)
    assert isinstance(treasury_scroll, QScrollArea)
    assert treasury_scroll.widgetResizable()
    assert treasury_scroll.objectName() == "treasuryAccountsScrollArea"
    statement_index = next(
        index
        for index in range(tabs.count())
        if tabs.tabText(index).strip() == "كشف حساب العميل"
    )
    statement_page = tabs.widget(statement_index)
    assert isinstance(statement_page, CustomerStatementPage)
    assert statement_page.objectName() == "customerStatementPage"

    manufacturing_index = window.page_indexes["التصنيع"]
    window.pages_changed(manufacturing_index)
    app.processEvents()
    manufacturing_page = window.pages.widget(manufacturing_index)
    manufacturing_buttons = {
        button.text().strip(): button
        for button in manufacturing_page.findChildren(QPushButton)
    }
    assert "خلطات التشغيل" in manufacturing_buttons
    assert "إضافة خلطة للأمر الجاري" not in manufacturing_buttons
    assert "إنشاء/فتح الخلطة الحالية" not in manufacturing_buttons
    assert "خلطة جديدة من السابقة بدون خامة" not in manufacturing_buttons
    assert "إنشاء خلطة جديدة" not in manufacturing_buttons
    assert "نسخ الخلطة الحالية" not in manufacturing_buttons
    assert "إضافة خلطة كاملة" not in manufacturing_buttons

    action_labels = (
        "بدء وصرف الخامات",
        "تسجيل الناتج وإتمام الأمر",
        "تعديل أو حذف أو إلغاء أمر التصنيع المحدد",
        "خلطات التشغيل",
    )
    action_buttons = [manufacturing_buttons[label] for label in action_labels]
    assert all(button.isVisible() for button in action_buttons)
    heights = {button.height() for button in action_buttons}
    y_positions = {
        button.mapTo(manufacturing_page, QPoint(0, 0)).y()
        for button in action_buttons
    }
    widths = [button.width() for button in action_buttons]
    assert len(heights) == 1
    assert next(iter(heights)) >= 44
    assert len(y_positions) == 1
    assert max(widths) - min(widths) <= 1

    window.close()
    app.processEvents()
