from PySide6.QtCore import QObject, QEvent, Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QPlainTextEdit,
    QTableWidget,
    QToolTip,
    QVBoxLayout,
    QWidget,
)


class _TableReadabilityFilter(QObject):
    def __init__(self, table: QTableWidget) -> None:
        super().__init__(table)
        self.table = table

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        try:
            viewport = self.table.viewport()
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


__all__ = ["configure_readable_table", "configure_tables_in_widget"]