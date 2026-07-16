from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter

from app.services.a4_invoice_renderer import A4InvoiceRenderer


class A4DocumentRenderer(A4InvoiceRenderer):
    def _draw_header(self, painter: QPainter, settings: dict[str, str]) -> None:
        super()._draw_header(painter, settings)

    def _draw_metadata(self, painter: QPainter, document: dict) -> None:
        original_columns = self.META_COLUMNS
        label = str(document.get("document_number_label") or "رقم الفاتورة")
        self.META_COLUMNS = tuple(
            (left, right, label if key == "invoice_number" else title, key)
            for left, right, title, key in original_columns
        )
        try:
            super()._draw_metadata(painter, document)
        finally:
            self.META_COLUMNS = original_columns

    def render(self, document: dict, settings: dict[str, str]):
        pages = super().render(document, settings)
        title = str(document.get("document_title") or "فاتورة مبيعات")
        if title == "فاتورة مبيعات":
            return pages

        for page in pages:
            painter = QPainter(page)
            painter.scale(self.OUTPUT_SCALE, self.OUTPUT_SCALE)
            try:
                painter.fillRect(QRect(255, 250, 545, 76), self.WHITE)
                self._draw_text(
                    painter,
                    QRect(255, 250, 545, 76),
                    title,
                    48,
                    self.BLUE,
                    bold=True,
                )
            finally:
                painter.end()
        return pages


__all__ = ["A4DocumentRenderer"]
