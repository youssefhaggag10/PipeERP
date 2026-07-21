import os
import secrets
from pathlib import Path

import pytest

if os.environ.get("PIPEERP_GUI_SMOKE") != "1":
    pytest.skip("GUI smoke tests run in the dedicated offscreen workflow", allow_module_level=True)


def test_offscreen_themes_and_core_windows_open_without_crash(tmp_path: Path) -> None:
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

    delegate = window.navigation.itemDelegate()
    assert isinstance(delegate, SalesNavigationDelegate)
    item_rect = window.navigation.visualItemRect(sales_item)
    arrow_rect = delegate.arrow_rect(item_rect)
    assert item_rect.contains(arrow_rect)
    assert arrow_rect.left() - item_rect.left() <= 20
    text_width = window.navigation.fontMetrics().horizontalAdvance("المبيعات")
    assert text_width < item_rect.right() - arrow_rect.right() - 12
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

    accounts_page = window.pages.widget(window.page_indexes["الحسابات"])
    tabs = accounts_page.findChild(QTabWidget)
    assert tabs is not None
    treasury_index = next(
        index
        for index in range(tabs.count())
        if tabs.tabText(index).strip() == "الخزينة والبنوك"
    )
    treasury_scroll = tabs.widget(treasury_index)
    assert isinstance(treasury_scroll, QScrollArea)
    assert treasury_scroll.widgetResizable()
    assert treasury_scroll.objectName() == "treasuryAccountsScrollArea"

    manufacturing_page = window.pages.widget(window.page_indexes["التصنيع"])
    manufacturing_buttons = {
        button.text().strip()
        for button in manufacturing_page.findChildren(QPushButton)
    }
    assert "خلطات التشغيل" in manufacturing_buttons
    assert "إضافة خلطة للأمر الجاري" not in manufacturing_buttons
    assert "إنشاء/فتح الخلطة الحالية" not in manufacturing_buttons
    assert "خلطة جديدة من السابقة بدون خامة" not in manufacturing_buttons
    assert "إنشاء خلطة جديدة" not in manufacturing_buttons
    assert "نسخ الخلطة الحالية" not in manufacturing_buttons
    assert "إضافة خلطة كاملة" not in manufacturing_buttons

    window.close()
    app.processEvents()
