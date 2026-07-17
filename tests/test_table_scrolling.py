import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip(
    "PySide6.QtGui",
    reason="The host does not provide the Qt EGL runtime",
    exc_type=ImportError,
)

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QAbstractItemView, QApplication, QTableWidget

from app.ui.table_readability import (
    DEFAULT_TABLE_MINIMUM_HEIGHT,
    _scroll_table_vertically,
    configure_readable_table,
    install_global_table_configuration,
)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_global_table_configuration_enables_clear_scrolling() -> None:
    app = _application()
    table = QTableWidget(20, 3)
    configure_readable_table(table)
    table.resize(420, DEFAULT_TABLE_MINIMUM_HEIGHT)
    table.show()
    app.processEvents()

    assert table.minimumHeight() >= DEFAULT_TABLE_MINIMUM_HEIGHT
    assert table.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert table.horizontalScrollBarPolicy() == Qt.ScrollBarAsNeeded
    assert table.verticalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert table.horizontalScrollMode() == QAbstractItemView.ScrollPerPixel
    assert table.verticalScrollBar().maximum() > 0


def test_mouse_wheel_moves_table_and_stops_at_scroll_edge() -> None:
    app = _application()
    table = QTableWidget(20, 3)
    configure_readable_table(table)
    table.resize(420, DEFAULT_TABLE_MINIMUM_HEIGHT)
    table.show()
    app.processEvents()

    wheel_down = QWheelEvent(
        QPointF(10, 10),
        QPointF(10, 10),
        QPoint(),
        QPoint(0, -120),
        Qt.NoButton,
        Qt.NoModifier,
        Qt.ScrollUpdate,
        False,
    )
    assert _scroll_table_vertically(table, wheel_down)
    assert table.verticalScrollBar().value() > 0

    table.verticalScrollBar().setValue(table.verticalScrollBar().maximum())
    assert not _scroll_table_vertically(table, wheel_down)


def test_global_filter_configures_tables_created_later() -> None:
    app = _application()
    install_global_table_configuration(app)

    table = QTableWidget(10, 2)
    table.show()
    app.processEvents()

    assert table.property("pipeerp_readability_configured") is True
    assert table.minimumHeight() >= DEFAULT_TABLE_MINIMUM_HEIGHT
