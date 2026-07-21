from __future__ import annotations

from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QPainter, QPalette
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
    """Paint a dropdown arrow inside a normal sales QListWidgetItem."""

    def arrow_rect(self, item_rect: QRect) -> QRect:
        view = self.parent()
        font_metrics = view.fontMetrics() if isinstance(view, QListWidget) else None
        font_height = font_metrics.height() if font_metrics is not None else 16
        arrow_size = max(11, min(18, font_height - 1))
        left_margin = max(7, round(font_height * 0.35))
        return QRect(
            item_rect.left() + left_margin,
            item_rect.center().y() - arrow_size // 2,
            arrow_size,
            arrow_size,
        )

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        if not bool(index.data(SALES_DROPDOWN_ROLE)):
            super().paint(painter, option, index)
            return

        styled = QStyleOptionViewItem(option)
        self.initStyleOption(styled, index)
        text = styled.text
        styled.text = ""
        style = styled.widget.style() if styled.widget is not None else QApplication.style()

        painter.save()
        style.drawControl(QStyle.CE_ItemViewItem, styled, painter, styled.widget)

        arrow = self.arrow_rect(styled.rect)
        arrow_option = QStyleOption()
        arrow_option.rect = arrow
        arrow_option.state = styled.state
        arrow_option.palette = styled.palette
        style.drawPrimitive(
            QStyle.PE_IndicatorArrowDown,
            arrow_option,
            painter,
            styled.widget,
        )

        spacing = max(8, round(styled.fontMetrics.height() * 0.4))
        text_rect = QRect(styled.rect)
        text_rect.setLeft(arrow.right() + spacing)
        text_rect.setRight(styled.rect.right() - spacing)
        elided = styled.fontMetrics.elidedText(text, Qt.ElideRight, max(0, text_rect.width()))
        color_role = (
            QPalette.HighlightedText
            if styled.state & QStyle.State_Selected
            else QPalette.Text
        )
        style.drawItemText(
            painter,
            text_rect,
            Qt.AlignRight | Qt.AlignVCenter,
            styled.palette,
            bool(styled.state & QStyle.State_Enabled),
            elided,
            color_role,
        )
        painter.restore()


class NavigationListWidget(QListWidget):
    sales_dropdown_requested = Signal(object, QPoint)

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
            # A selected QListWidgetItem does not normally emit currentItemChanged
            # again. Re-emitting it makes clicking the sales text always reopen
            # normal sales after the weight page was opened from the arrow menu.
            self.currentItemChanged.emit(item, item)


__all__ = [
    "NavigationListWidget",
    "SALES_DROPDOWN_ROLE",
    "SalesNavigationDelegate",
]
