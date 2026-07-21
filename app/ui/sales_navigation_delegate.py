from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QApplication,
    QListWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOption,
    QStyleOptionViewItem,
)

SALES_DROPDOWN_ROLE = Qt.UserRole + 1


class SalesNavigationDelegate(QStyledItemDelegate):
    """Paint a compact dropdown arrow inside a normal sales QListWidgetItem."""

    def arrow_rect(self, item_rect: QRect) -> QRect:
        view = self.parent()
        font_metrics = view.fontMetrics() if isinstance(view, QListWidget) else None
        font_height = font_metrics.height() if font_metrics is not None else 16
        arrow_size = max(10, min(14, font_height - 3))
        left_margin = max(9, round(font_height * 0.45))
        return QRect(
            item_rect.left() + left_margin,
            item_rect.center().y() - arrow_size // 2,
            arrow_size,
            arrow_size,
        )

    def text_rect(self, item_rect: QRect, font_height: int) -> QRect:
        arrow = self.arrow_rect(item_rect)
        spacing = max(10, round(font_height * 0.5))
        rect = QRect(item_rect)
        rect.setLeft(arrow.right() + spacing)
        rect.setRight(item_rect.right() - spacing)
        return rect

    def item_style_option(
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> QStyleOptionViewItem:
        """Return Qt's native item option without overriding RTL alignment."""
        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        return styled

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if not bool(index.data(SALES_DROPDOWN_ROLE)):
            super().paint(painter, option, index)
            return

        styled = self.item_style_option(option, index)
        style = styled.widget.style() if styled.widget is not None else QApplication.style()

        painter.save()
        # Qt keeps the Arabic sales label aligned exactly like every normal
        # navigation item. Only the separate dropdown arrow is custom-painted.
        style.drawControl(QStyle.CE_ItemViewItem, styled, painter, styled.widget)

        arrow_option = QStyleOption()
        arrow_option.rect = self.arrow_rect(styled.rect)
        arrow_option.state = styled.state
        arrow_option.palette = styled.palette
        style.drawPrimitive(
            QStyle.PE_IndicatorArrowDown,
            arrow_option,
            painter,
            styled.widget,
        )
        painter.restore()


class NavigationListWidget(QListWidget):
    sales_dropdown_requested = Signal(object, QPoint)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setUniformItemSizes(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.ElideNone)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def mousePressEvent(self, event) -> None:
        position = event.position().toPoint()
        index = self.indexAt(position)
        item = self.item(index.row()) if index.isValid() else None
        is_sales_item = bool(index.data(SALES_DROPDOWN_ROLE)) if index.isValid() else False
        delegate = self.itemDelegate()
        if is_sales_item and isinstance(delegate, SalesNavigationDelegate):
            item_rect = self.visualRect(index)
            if delegate.arrow_rect(item_rect).contains(position):
                global_position = self.viewport().mapToGlobal(
                    QPoint(item_rect.left(), item_rect.bottom())
                )
                self.sales_dropdown_requested.emit(item, global_position)
                event.accept()
                return

        was_current_sales = is_sales_item and item is not None and self.currentItem() is item
        super().mousePressEvent(event)
        if was_current_sales:
            # A selected item does not emit currentItemChanged again. Re-emitting it
            # makes clicking the sales text reopen normal sales after weight sales.
            self.currentItemChanged.emit(item, item)


__all__ = [
    "NavigationListWidget",
    "SALES_DROPDOWN_ROLE",
    "SalesNavigationDelegate",
]
