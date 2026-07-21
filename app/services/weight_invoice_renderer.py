from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QPainter, QPen

from app.services.a4_invoice_renderer import A4InvoiceRenderer


class WeightInvoiceRenderer(A4InvoiceRenderer):
    """Render the approved 3A weight-card invoice as a separate A4 document."""

    ROWS_PER_PAGE = 6
    META_COLUMNS = (
        (31, 160, "السيارة/الحمولة", "vehicle_number"),
        (160, 300, "رقم الكارتة", "card_number"),
        (300, 440, "العميل", "customer_name"),
        (440, 570, "الهاتف", "customer_phone"),
        (570, 715, "التاريخ", "invoice_date"),
        (715, 863, "رقم الأمر", "order_number"),
        (863, 1021, "رقم الفاتورة", "invoice_number"),
    )
    ITEM_COLUMNS = (
        (31, 205, "ملاحظات", "notes"),
        (205, 350, "الإجمالي", "line_total"),
        (350, 515, "وزن الكارتة", "actual_weight_kg"),
        (515, 620, "الكمية", "quantity"),
        (620, 735, "الوحدة", "unit"),
        (735, 955, "البيان", "name"),
        (955, 1020, "م", "serial"),
    )

    def _draw_header(self, painter: QPainter, settings: dict[str, str]) -> None:
        super()._draw_header(painter, settings)
        painter.fillRect(QRect(255, 250, 545, 76), self.WHITE)
        self._draw_text(
            painter,
            QRect(255, 250, 545, 76),
            "فاتورة مبيعات بالوزن / الكارتة",
            46,
            self.BLUE,
            bold=True,
            min_size=28,
        )

    def _draw_metadata(self, painter: QPainter, invoice: dict) -> None:
        date_value, time_value = self._date_parts(invoice.get("invoice_date"))
        values = dict(invoice)
        values["vehicle_number"] = values.get("vehicle_number") or "—"
        values["invoice_date"] = date_value
        values["invoice_time"] = time_value
        values["payment_methods"] = invoice.get("payment_methods") or "—"

        for left, right, label, key in self.META_COLUMNS:
            self._draw_text(
                painter,
                QRect(left + 3, 351, right - left - 6, 45),
                label,
                18,
                self.WHITE,
                bold=True,
            )
            value_padding = 14 if key == "card_number" else 5
            self._draw_text(
                painter,
                QRect(
                    left + value_padding,
                    459,
                    right - left - (value_padding * 2),
                    39,
                ),
                str(values.get(key, "") or "—"),
                13 if key == "card_number" else 16,
                self.BLACK,
                bold=True,
                min_size=9 if key == "card_number" else 11,
            )

    def _draw_items(
        self,
        painter: QPainter,
        lines: list[dict],
        *,
        serial_offset: int,
    ) -> None:
        for left, right, label, _ in self.ITEM_COLUMNS:
            self._draw_text(
                painter,
                QRect(left + 7, 522, right - left - 14, 52),
                label,
                17,
                self.WHITE if label != "م" else self.BLACK,
                bold=True,
                min_size=10,
            )

        body_top, body_bottom = 576, 776
        visible_rows = max(3, len(lines))
        row_height = (body_bottom - body_top) / visible_rows
        painter.fillRect(QRect(32, body_top, 987, body_bottom - body_top), self.WHITE)
        painter.setPen(QPen(self.GRID, 1))
        for left, _, _, _ in self.ITEM_COLUMNS:
            painter.drawLine(left, body_top, left, body_bottom)
        painter.drawLine(1020, body_top, 1020, body_bottom)
        for row_index in range(visible_rows + 1):
            y = round(body_top + row_index * row_height)
            painter.drawLine(31, y, 1020, y)

        for row_index, line in enumerate(lines):
            top = round(body_top + row_index * row_height)
            bottom = round(body_top + (row_index + 1) * row_height)
            values = {
                "notes": str(line.get("notes", "") or ""),
                "line_total": self._money(line.get("line_total")),
                "actual_weight_kg": f"{float(line.get('actual_weight_kg', 0) or 0):,.3f}",
                "quantity": f"{float(line.get('quantity', 0) or 0):g}",
                "unit": str(line.get("unit", "") or "ماسورة"),
                "name": self._product_text(line),
                "serial": str(serial_offset + row_index + 1),
            }
            for left, right, _, key in self.ITEM_COLUMNS:
                self._draw_text(
                    painter,
                    QRect(left + 8, top + 7, right - left - 16, bottom - top - 14),
                    values[key],
                    16 if key not in {"name", "notes"} else 15,
                    self.BLACK,
                    bold=True,
                    min_size=9,
                )

__all__ = ["WeightInvoiceRenderer"]
