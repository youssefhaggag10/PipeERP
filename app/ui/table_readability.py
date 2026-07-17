from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QPlainTextEdit,
    QSizePolicy,
    QTableWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

DEFAULT_TABLE_MINIMUM_HEIGHT = 150
DEFAULT_SCROLL_STEP = 36


def _scroll_table_vertically(table: QTableWidget, event: QEvent) -> bool:
    """Scroll a table reliably and let a parent scroll area take over at the edge."""
    scroll_bar = table.verticalScrollBar()
    if scroll_bar.maximum() <= scroll_bar.minimum():
        return False

    pixel_delta = event.pixelDelta().y()
    angle_delta = event.angleDelta().y()
    if pixel_delta:
        distance = abs(pixel_delta)
        direction = 1 if pixel_delta > 0 else -1
    elif angle_delta:
        notches = max(1, abs(angle_delta) // 120)
        distance = DEFAULT_SCROLL_STEP * notches
        direction = 1 if angle_delta > 0 else -1
    else:
        return False

    old_value = scroll_bar.value()
    new_value = max(
        scroll_bar.minimum(),
        min(scroll_bar.maximum(), old_value - (direction * distance)),
    )
    if new_value == old_value:
        return False
    scroll_bar.setValue(new_value)
    return True


class _TableReadabilityFilter(QObject):
    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self.table = table

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        try:
            viewport = self.table.viewport()
            if watched is viewport and event.type() == QEvent.Wheel:
                if _scroll_table_vertically(self.table, event):
                    event.accept()
                    return True
            if watched is viewport and event.type() == QEvent.MouseMove:
                item = self.table.itemAt(event.position().toPoint())
                if item is None or not item.text().strip():
                    QToolTip.hideText()
                else:
                    QToolTip.showText(
                        event.globalPosition().toPoint(),
                        item.text(),
                        self.table,
                    )
        except RuntimeError:
            # Qt may dispatch a final event while the parent table is already
            # being destroyed during application shutdown or failed startup.
            return False
        return super().eventFilter(watched, event)


class _GlobalTableConfigurationFilter(QObject):
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, QTableWidget) and event.type() in {
            QEvent.Polish,
            QEvent.Show,
        }:
            configure_readable_table(watched)
        return super().eventFilter(watched, event)


def _show_full_cell_text(table: QTableWidget, row: int, column: int) -> None:
    item = table.item(row, column)
    if item is None or not item.text().strip():
        return

    header_item = table.horizontalHeaderItem(column)
    title = header_item.text() if header_item is not None else "تفاصيل الخلية"

    dialog = QDialog(table)
    dialog.setWindowTitle(title)
    dialog.resize(650, 320)
    dialog.setLayoutDirection(Qt.RightToLeft)

    editor = QPlainTextEdit()
    editor.setReadOnly(True)
    editor.setPlainText(item.text())
    editor.setTextInteractionFlags(
        Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard
    )

    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)

    layout = QVBoxLayout(dialog)
    layout.addWidget(editor)
    layout.addWidget(buttons)
    dialog.exec()


def configure_readable_table(table: QTableWidget) -> None:
    if bool(table.property("pipeerp_readability_configured")):
        return
    table.setProperty("pipeerp_readability_configured", True)

    header = table.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(70)
    header.setSectionsMovable(False)

    table.setTextElideMode(Qt.ElideRight)
    table.setMouseTracking(True)
    table.setWordWrap(False)
    table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
    table.setMinimumHeight(
        max(table.minimumHeight(), DEFAULT_TABLE_MINIMUM_HEIGHT)
    )
    table.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
    table.verticalScrollBar().setSingleStep(DEFAULT_SCROLL_STEP)
    table.horizontalScrollBar().setSingleStep(DEFAULT_SCROLL_STEP)

    for column in range(table.columnCount()):
        header_item = table.horizontalHeaderItem(column)
        title = "" if header_item is None else header_item.text().strip()
        if "ملاحظ" in title or "بيان" in title or "وصف" in title:
            table.setColumnWidth(column, 340)
        elif table.columnWidth(column) < 115:
            table.setColumnWidth(column, 130)

    table.cellDoubleClicked.connect(
        lambda row, column, current_table=table: _show_full_cell_text(
            current_table, row, column
        )
    )

    readability_filter = _TableReadabilityFilter(table)
    table.viewport().installEventFilter(readability_filter)
    table._pipeerp_readability_filter = readability_filter


def configure_tables_in_widget(widget: QWidget) -> None:
    if isinstance(widget, QTableWidget):
        configure_readable_table(widget)
    for table in widget.findChildren(QTableWidget):
        configure_readable_table(table)


def install_global_table_configuration(application: QApplication) -> None:
    """Apply the same scrolling and readability rules to every present/future table."""
    if bool(application.property("pipeerp_global_tables_configured")):
        return
    application.setProperty("pipeerp_global_tables_configured", True)
    global_filter = _GlobalTableConfigurationFilter(application)
    application.installEventFilter(global_filter)
    application._pipeerp_global_table_filter = global_filter
    for widget in application.allWidgets():
        if isinstance(widget, QTableWidget):
            configure_readable_table(widget)


__all__ = [
    "DEFAULT_TABLE_MINIMUM_HEIGHT",
    "configure_readable_table",
    "configure_tables_in_widget",
    "install_global_table_configuration",
]
