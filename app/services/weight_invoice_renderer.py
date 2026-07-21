from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QPainter, QPen

from app.services.a4_invoice_renderer import A4InvoiceRenderer


class WeightInvoiceRenderer(A4InvoiceRenderer):
    """Render the approved 3A weight-card invoice as a separate A4 document."""

    ROWS_PER_PAGE = 8
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
        (31, 172, "ملاحظات", "notes"),
        (172, 302, "الإجمالي", "line_total"),
        (302, 414, "سعر الكيلو", "price_per_kg"),
        (414, 548, "الوزن الفعلي", "actual_weight_kg"),
        (548, 642, "الكمية", "quantity"),
        (642, 742, "الوحدة", "unit"),
        (742, 955, "البيان", "name"),
        (955, 1020, "م", "serial"),
    )

    def _draw_header(self, painter: QPainter, settings: dict[str, str]) -> None:
        super()._draw_header(painter, settings)
        painter.fillRect(QRect(255, 250, 545, 76), self.WHITE)
        self._draw_text(
            painter,
            QRect(255, 250, 545, 76),
            "فاتورة مبيعات بالوزن / الكارتة",
            40,
            self.BLUE,
            bold=True,
            min_size=28,
        )

    def _draw_metadata(self, painter: QPainter, invoice: dict) -> None:
        values = dict(invoice)
        values["vehicle_number"] = values.get("vehicle_number") or "—"
        super()._draw_metadata(painter, values)

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
                QRect(left + 3, 522, right - left - 6, 52),
                label,
                16,
                self.WHITE if label != "م" else self.BLACK,
                bold=True,
                min_size=11,
            )

        body_top, body_bottom = 576, 802
        visible_rows = max(4, len(lines))
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
                "price_per_kg": self._money(line.get("price_per_kg")),
                "actual_weight_kg": f"{float(line.get('actual_weight_kg', 0) or 0):,.3f}",
                "quantity": f"{float(line.get('quantity', 0) or 0):g}",
                "unit": str(line.get("unit", "") or "ماسورة"),
                "name": self._product_text(line),
                "serial": str(serial_offset + row_index + 1),
            }
            for left, right, _, key in self.ITEM_COLUMNS:
                self._draw_text(
                    painter,
                    QRect(left + 4, top + 2, right - left - 8, bottom - top - 4),
                    values[key],
                    15 if key not in {"name", "notes"} else 14,
                    self.BLACK,
                    bold=True,
                    min_size=9,
                )

    def _draw_totals(self, painter: QPainter, invoice: dict) -> None:
        subtotal = float(invoice.get("subtotal", invoice.get("total", 0)) or 0)
        discount = float(invoice.get("discount_amount", 0) or 0)
        transport = float(invoice.get("transport_amount", 0) or 0)
        tax = float(invoice.get("tax_amount", 0) or 0)
        net_total = float(invoice.get("net_total", invoice.get("total", 0)) or 0)
        paid = float(invoice.get("paid", 0) or 0)
        remaining = float(invoice.get("remaining", 0) or 0)
        pieces = float(invoice.get("total_pieces", 0) or 0)
        weight = float(invoice.get("net_weight_kg", 0) or 0)

        painter.fillRect(QRect(60, 818, 900, 228), self.YELLOW)
        summaries = (
            ("إجمالي عدد المواسير", f"{pieces:g}"),
            ("إجمالي الوزن الفعلي", f"{weight:,.3f} كجم"),
            ("إجمالي البنود", f"{subtotal:,.2f}"),
            ("الخصم", f"{discount:,.2f}"),
            ("النقل", f"{transport:,.2f}"),
            ("الضريبة", f"{tax:,.2f}"),
            ("صافي الفاتورة", f"{net_total:,.2f}"),
            ("المدفوع لهذه الفاتورة", f"{paid:,.2f}"),
            ("المتبقي على هذه الفاتورة", f"{remaining:,.2f}"),
        )
        columns = 3
        cell_width = 286
        cell_height = 68
        for index, (label, value) in enumerate(summaries):
            row = index // columns
            column = index % columns
            left = 80 + column * cell_width
            top = 830 + row * cell_height
            self._draw_text(
                painter,
                QRect(left, top, cell_width - 12, 28),
                label,
                15,
                self.BLACK,
                bold=True,
                min_size=11,
            )
            self._draw_text(
                painter,
                QRect(left, top + 27, cell_width - 12, 34),
                value,
                21,
                self.DARK_BLUE if label != "المتبقي على هذه الفاتورة" else self.GREEN,
                bold=True,
                min_size=14,
            )

    def _draw_terms(self, painter: QPainter) -> None:
        self._draw_text(
            painter,
            QRect(55, 1065, 920, 120),
            "ملاحظات الفاتورة:\n"
            "• القيمة النهائية محسوبة من الوزن الفعلي فقط.\n"
            "• الوزن القياسي والنظري بيانات مرجعية ولا يدخلان في قيمة الفاتورة.\n"
            "• الرصيد الظاهر يخص هذه الفاتورة فقط، أما الرصيد الكامل فيظهر بكشف حساب العميل.",
            18,
            self.BLACK,
            bold=True,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            min_size=13,
        )


__all__ = ["WeightInvoiceRenderer"]
