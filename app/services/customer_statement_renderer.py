from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPen

from app.services.a4_invoice_renderer import A4InvoiceRenderer


class CustomerStatementRenderer(A4InvoiceRenderer):
    """Render a customer ledger independently from any single sales invoice."""

    PAGE_ROW_CAPACITY = 9.0
    DETAIL_ROW_WEIGHT = 0.82
    TABLE_BOTTOM = 1265
    PALE_BLUE = QColor("#eef5fd")
    SOFT_GRAY = QColor("#f5f7fa")
    MUTED = QColor("#4f5e70")
    BORDER_BLUE = QColor("#2865a6")
    COLUMNS = (
        (31, 142, "الحالة", "status"),
        (142, 260, "الرصيد", "running_balance"),
        (260, 370, "دائن", "credit"),
        (370, 480, "مدين", "debit"),
        (480, 720, "البيان", "description"),
        (720, 845, "نوع المستند", "document_type"),
        (845, 950, "رقم المستند", "document_number"),
        (950, 1020, "التاريخ", "movement_date"),
    )

    def render(self, statement: dict, settings: dict[str, str]) -> list[QImage]:
        source = QImage(str(self.background_path))
        if source.isNull():
            raise ValueError("تعذر تحميل تصميم مستند A4")
        background = source.scaled(
            source.width() * self.OUTPUT_SCALE,
            source.height() * self.OUTPUT_SCALE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        flattened = self._flatten_rows(statement)
        chunks = self._paginate_rows(flattened)
        total_pages = len(chunks) + 1
        pages: list[QImage] = []
        for page_index, chunk in enumerate(chunks):
            page = background.copy()
            painter = QPainter(page)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.scale(self.OUTPUT_SCALE, self.OUTPUT_SCALE)
            try:
                self._draw_header(painter, settings)
                self._draw_statement_title(painter)
                self._clear_document_body(painter)
                self._draw_statement_metadata(painter, statement)
                self._draw_statement_rows(painter, chunk)
                self._draw_footer(painter, settings, page_index + 1, total_pages)
            finally:
                painter.end()
            pages.append(page)

        summary_page = background.copy()
        painter = QPainter(summary_page)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        painter.scale(self.OUTPUT_SCALE, self.OUTPUT_SCALE)
        try:
            self._draw_header(painter, settings)
            self._draw_summary_title(painter)
            self._clear_document_body(painter)
            self._draw_summary_metadata(painter, statement)
            self._draw_statement_summary(painter, statement)
            self._draw_footer(painter, settings, total_pages, total_pages)
        finally:
            painter.end()
        pages.append(summary_page)
        return pages

    def _clear_document_body(self, painter: QPainter) -> None:
        """Remove invoice-only artwork while preserving the branded footer."""
        painter.fillRect(QRect(31, 342, 989, 968), self.WHITE)

    def _paginate_rows(self, rows: list[dict]) -> list[list[dict]]:
        if not rows:
            return [[]]
        pages: list[list[dict]] = []
        page: list[dict] = []
        used = 0.0
        for row in rows:
            weight = self.DETAIL_ROW_WEIGHT if row.get("is_detail") else 1.0
            if page and used + weight > self.PAGE_ROW_CAPACITY:
                pages.append(page)
                page = []
                used = 0.0
            page.append(row)
            used += weight
        if page:
            pages.append(page)
        return pages

    def _draw_statement_title(self, painter: QPainter) -> None:
        painter.fillRect(QRect(255, 250, 545, 76), self.WHITE)
        self._draw_text(
            painter,
            QRect(255, 250, 545, 76),
            "كشف حساب عميل",
            48,
            self.BLUE,
            bold=True,
        )

    def _draw_summary_title(self, painter: QPainter) -> None:
        painter.fillRect(QRect(255, 250, 545, 76), self.WHITE)
        self._draw_text(
            painter,
            QRect(255, 250, 545, 76),
            "ملخص كشف حساب العميل",
            43,
            self.BLUE,
            bold=True,
            min_size=28,
        )

    def _draw_statement_metadata(self, painter: QPainter, statement: dict) -> None:
        customer = statement.get("customer", {})
        # The source A4 template contains invoice-specific icons in this zone.
        # Cover it first so statement metadata and opening balance stay clean.
        painter.fillRect(QRect(31, 342, 989, 148), self.WHITE)
        values = (
            (31, 260, "العميل", customer.get("name", "—")),
            (260, 440, "كود العميل", customer.get("code", "—")),
            (440, 620, "الهاتف", customer.get("phone", "—")),
            (620, 820, "من تاريخ", statement.get("date_from", "—")),
            (820, 1020, "إلى تاريخ", statement.get("date_to", "—")),
        )
        painter.setPen(QPen(self.GRID, 1))
        for left, right, label, value in values:
            painter.fillRect(QRect(left, 350, right - left, 44), self.DARK_BLUE)
            painter.fillRect(QRect(left, 394, right - left, 44), self.WHITE)
            painter.drawRect(QRect(left, 350, right - left, 88))
            self._draw_text(
                painter,
                QRect(left + 4, 350, right - left - 8, 44),
                label,
                17,
                self.WHITE,
                bold=True,
                min_size=12,
            )
            self._draw_text(
                painter,
                QRect(left + 4, 394, right - left - 8, 44),
                str(value or "—"),
                16,
                self.BLACK,
                bold=True,
                min_size=10,
            )
        opening = float(statement.get("opening_balance", 0) or 0)
        painter.fillRect(QRect(31, 446, 989, 42), self.WHITE)
        painter.drawRect(QRect(31, 446, 989, 42))
        self._draw_text(
            painter,
            QRect(45, 446, 961, 42),
            f"رصيد أول المدة: {opening:,.2f} جنيه - "
            + ("كشف تفصيلي" if statement.get("detailed") else "كشف مختصر"),
            20,
            self.DARK_BLUE,
            bold=True,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

    def _draw_summary_metadata(self, painter: QPainter, statement: dict) -> None:
        customer = statement.get("customer", {})
        painter.fillRect(QRect(31, 342, 989, 148), self.WHITE)
        values = (
            (31, 300, "العميل", customer.get("name", "—")),
            (300, 510, "كود العميل", customer.get("code", "—")),
            (510, 720, "الهاتف", customer.get("phone", "—")),
            (
                720,
                1020,
                "الفترة",
                f"{statement.get('date_from', '—')} إلى {statement.get('date_to', '—')}",
            ),
        )
        painter.setPen(QPen(self.GRID, 1))
        for left, right, label, value in values:
            painter.fillRect(QRect(left, 350, right - left, 42), self.DARK_BLUE)
            painter.fillRect(QRect(left, 392, right - left, 48), self.WHITE)
            painter.drawRect(QRect(left, 350, right - left, 90))
            self._draw_text(
                painter,
                QRect(left + 8, 350, right - left - 16, 42),
                label,
                16,
                self.WHITE,
                bold=True,
                min_size=11,
            )
            self._draw_text(
                painter,
                QRect(left + 9, 397, right - left - 18, 38),
                str(value or "—"),
                16,
                self.BLACK,
                bold=True,
                min_size=10,
            )

    def _draw_statement_rows(self, painter: QPainter, rows: list[dict]) -> None:
        header_top = 500
        body_top, body_bottom = 544, self.TABLE_BOTTOM
        for left, right, label, _ in self.COLUMNS:
            painter.fillRect(QRect(left, header_top, right - left, 44), self.DARK_BLUE)
            self._draw_text(
                painter,
                QRect(left + 6, header_top, right - left - 12, 44),
                label,
                15,
                self.WHITE,
                bold=True,
                min_size=10,
            )
        row_weights = [
            self.DETAIL_ROW_WEIGHT if row.get("is_detail") else 1.0 for row in rows
        ]
        used_weight = sum(row_weights)
        layout_weight = max(7.0, used_weight)
        unit_height = (body_bottom - body_top) / layout_weight
        content_bottom = round(body_top + used_weight * unit_height)
        painter.fillRect(QRect(31, body_top, 989, body_bottom - body_top), self.WHITE)
        painter.setPen(QPen(self.GRID, 1))
        painter.drawRect(QRect(31, body_top, 989, max(1, content_bottom - body_top)))

        cursor = float(body_top)
        for row_index, row in enumerate(rows):
            top = round(cursor)
            cursor += row_weights[row_index] * unit_height
            bottom = round(cursor)
            detail = bool(row.get("is_detail"))
            if detail:
                self._draw_detail_row(painter, row, top, bottom)
                continue
            painter.fillRect(
                QRect(31, top, 989, bottom - top),
                self.WHITE if row_index % 2 == 0 else self.SOFT_GRAY,
            )
            painter.setPen(QPen(self.GRID, 1))
            painter.drawLine(31, top, 1020, top)
            for left, _, _, _ in self.COLUMNS:
                painter.drawLine(left, top, left, bottom)
            painter.drawLine(1020, top, 1020, bottom)
            values = {
                "status": str(row.get("status", "") or ""),
                "running_balance": (
                    "" if detail else f"{float(row.get('running_balance', 0) or 0):,.2f}"
                ),
                "credit": "" if detail else self._money(row.get("credit")),
                "debit": "" if detail else self._money(row.get("debit")),
                "description": str(row.get("description", "") or ""),
                "document_type": str(row.get("document_type", "") or ""),
                "document_number": str(row.get("document_number", "") or ""),
                "movement_date": str(row.get("movement_date", "") or "")[:10],
            }
            for left, right, _, key in self.COLUMNS:
                self._draw_text(
                    painter,
                    QRect(left + 7, top + 6, right - left - 14, bottom - top - 12),
                    values[key],
                    15,
                    self.BLACK,
                    bold=True,
                    min_size=9,
                )
        if rows:
            painter.setPen(QPen(self.GRID, 1))
            painter.drawLine(31, content_bottom, 1020, content_bottom)

    def _draw_detail_row(
        self,
        painter: QPainter,
        row: dict,
        top: int,
        bottom: int,
    ) -> None:
        painter.fillRect(QRect(31, top, 989, bottom - top), self.PALE_BLUE)
        painter.setPen(QPen(self.BORDER_BLUE, 1))
        painter.drawRect(QRect(31, top, 989, bottom - top))

        weight = row.get("actual_weight_kg")
        price = row.get("price")
        value_label = "سعر الكيلو" if weight is not None else "سعر الوحدة"
        weight_text = (
            f"وزن الكارتة: {float(weight):,.3f} كجم" if weight is not None else ""
        )
        blocks = (
            (42, 135, "بند فاتورة", self.DARK_BLUE, self.WHITE),
            (145, 520, str(row.get("line_description", "") or "—"), self.BLACK, None),
            (
                530,
                690,
                f"الكمية: {float(row.get('quantity', 0) or 0):g} {row.get('unit', '')}\n{weight_text}",
                self.MUTED,
                None,
            ),
            (
                700,
                850,
                f"{value_label}: {float(price or 0):,.2f}",
                self.MUTED,
                None,
            ),
            (
                860,
                1008,
                f"الإجمالي\n{float(row.get('line_total', 0) or 0):,.2f}",
                self.DARK_BLUE,
                None,
            ),
        )
        notes = str(row.get("notes", "") or "").strip()
        for left, right, text, color, background in blocks:
            block_bottom = bottom - 28 if notes and 145 <= left < 850 else bottom - 8
            rect = QRect(
                left,
                top + 8,
                right - left,
                max(24, block_bottom - top - 8),
            )
            if background is not None:
                painter.fillRect(rect, background)
            self._draw_text(
                painter,
                rect.adjusted(6, 4, -6, -4),
                text,
                13,
                color,
                bold=True,
                min_size=8,
            )
        if notes:
            self._draw_text(
                painter,
                QRect(145, bottom - 25, 705, 20),
                f"ملاحظات: {notes}",
                10,
                self.MUTED,
                bold=False,
                min_size=7,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            )

    def _draw_statement_summary(self, painter: QPainter, statement: dict) -> None:
        summary = statement.get("summary", {})
        values = (
            ("رصيد أول المدة", summary.get("opening_balance", 0)),
            ("فواتير البيع العادية", summary.get("standard_sales_total", 0)),
            ("فواتير البيع بالوزن", summary.get("weight_sales_total", 0)),
            ("مرتجعات المبيعات", summary.get("returns_total", 0)),
            ("إجمالي التحصيلات", summary.get("receipts_total", 0)),
            ("الخصومات والتسويات", summary.get("adjustments_total", 0)),
            ("صافي الحركة", summary.get("net_movement", 0)),
            ("الرصيد النهائي المستحق", summary.get("closing_balance", 0)),
        )
        painter.fillRect(QRect(55, 485, 920, 62), self.YELLOW)
        self._draw_text(
            painter,
            QRect(75, 493, 880, 46),
            "ملخص الحركة المالية خلال الفترة",
            25,
            self.DARK_BLUE,
            bold=True,
            min_size=18,
        )
        for index, (label, value) in enumerate(values):
            row = index // 2
            column = index % 2
            left = 55 + column * 470
            top = 575 + row * 150
            card_color = self.PALE_BLUE if index != 7 else QColor("#edf8ef")
            border_color = self.BORDER_BLUE if index != 7 else self.GREEN
            painter.fillRect(QRect(left, top, 450, 118), card_color)
            painter.setPen(QPen(border_color, 2))
            painter.drawRoundedRect(QRect(left, top, 450, 118), 10, 10)
            painter.fillRect(QRect(left + 432, top, 18, 118), self.YELLOW)
            self._draw_text(
                painter,
                QRect(left + 190, top + 18, 225, 34),
                label,
                17,
                self.BLACK,
                bold=True,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                min_size=11,
            )
            self._draw_text(
                painter,
                QRect(left + 25, top + 48, 390, 48),
                f"{float(value or 0):,.2f} جنيه",
                24,
                border_color,
                bold=True,
                min_size=15,
            )

    @staticmethod
    def _flatten_rows(statement: dict) -> list[dict]:
        result: list[dict] = []
        for movement in statement.get("movements", []):
            result.append(dict(movement))
            for line in movement.get("lines", []) or []:
                quantity = float(line.get("quantity", 0) or 0)
                weight = line.get("actual_weight_kg")
                price = line.get("price_per_kg", line.get("unit_price", 0))
                detail_parts = [
                    str(line.get("description", "") or ""),
                    f"الكمية {quantity:g} {line.get('unit', '')}",
                ]
                if weight is not None:
                    detail_parts.append(f"الوزن {float(weight):,.3f} كجم")
                    detail_parts.append(f"سعر الكيلو {float(price or 0):,.2f}")
                else:
                    detail_parts.append(f"سعر الوحدة {float(price or 0):,.2f}")
                detail_parts.append(f"الإجمالي {float(line.get('line_total', 0) or 0):,.2f}")
                if line.get("notes"):
                    detail_parts.append(str(line["notes"]))
                result.append(
                    {
                        "is_detail": True,
                        "movement_date": "",
                        "document_number": "",
                        "document_type": "بند فاتورة",
                        "description": " - ".join(detail_parts),
                        "line_description": str(line.get("description", "") or ""),
                        "quantity": quantity,
                        "unit": str(line.get("unit", "") or ""),
                        "actual_weight_kg": weight,
                        "price": price,
                        "line_total": float(line.get("line_total", 0) or 0),
                        "notes": str(line.get("notes", "") or ""),
                        "debit": 0,
                        "credit": 0,
                        "running_balance": movement.get("running_balance", 0),
                        "status": "",
                    }
                )
        return result


__all__ = ["CustomerStatementRenderer"]
