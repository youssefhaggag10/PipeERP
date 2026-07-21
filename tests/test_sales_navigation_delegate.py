import os

import pytest

if os.environ.get("PIPEERP_GUI_SMOKE") != "1":
    pytest.skip("GUI smoke tests run in the dedicated offscreen workflow", allow_module_level=True)


def test_sales_item_stays_native_and_arrow_has_separate_click_area() -> None:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication, QListWidgetItem

    from app.ui.sales_navigation_delegate import (
        SALES_DROPDOWN_ROLE,
        NavigationListWidget,
        SalesNavigationDelegate,
    )

    app = QApplication.instance() or QApplication([])
    navigation = NavigationListWidget()
    navigation.setFixedWidth(240)
    font = navigation.font()
    font.setPointSize(18)
    navigation.setFont(font)
    delegate = SalesNavigationDelegate(navigation)
    navigation.setItemDelegate(delegate)

    normal_item = QListWidgetItem("المشتريات")
    sales_item = QListWidgetItem("المبيعات")
    sales_item.setData(SALES_DROPDOWN_ROLE, True)
    navigation.addItem(normal_item)
    navigation.addItem(sales_item)
    navigation.show()
    app.processEvents()

    assert navigation.itemWidget(sales_item) is None
    normal_rect = navigation.visualItemRect(normal_item)
    sales_rect = navigation.visualItemRect(sales_item)
    assert normal_rect.height() == sales_rect.height()

    arrow_rect = delegate.arrow_rect(sales_rect)
    assert sales_rect.contains(arrow_rect)
    assert arrow_rect.left() - sales_rect.left() <= 20
    text_width = navigation.fontMetrics().horizontalAdvance("المبيعات")
    assert text_width < sales_rect.right() - arrow_rect.right() - 12

    navigation.setCurrentItem(sales_item)
    app.processEvents()
    changed_items = []
    dropdown_requests = []
    navigation.currentItemChanged.connect(
        lambda current, _previous: changed_items.append(current)
    )
    navigation.sales_dropdown_requested.connect(
        lambda item, _position: dropdown_requests.append(item)
    )

    QTest.mouseClick(
        navigation.viewport(),
        Qt.MouseButton.LeftButton,
        pos=sales_rect.center(),
    )
    app.processEvents()
    assert changed_items == [sales_item]
    assert dropdown_requests == []

    changed_items.clear()
    QTest.mouseClick(
        navigation.viewport(),
        Qt.MouseButton.LeftButton,
        pos=arrow_rect.center(),
    )
    app.processEvents()
    assert changed_items == []
    assert dropdown_requests == [sales_item]

    navigation.close()
    app.processEvents()
