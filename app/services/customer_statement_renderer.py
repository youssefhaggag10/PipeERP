from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QImage, QPainter, QPen

from app.services.a4_invoice_renderer import A4InvoiceRenderer


class CustomerStatementRenderer(A4InvoiceRenderer):
    """Render a customer ledger independently from any single sales invoice."""

    ROWS_PER_PAGE = 17
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
        chunks = [
            flattened[index : index + self.ROWS_PER_PAGE]
            for index in range(0, max(1, len(flattened)), self.ROWS_PER_PAGE)
        ] or [[]]
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
                self._draw_statement_metadata(painter, statement)
                self._draw_statement_rows(painter, chunk)
                if page_index == len(chunks) - 1:
                    self._draw_statement_summary(painter, statement)
                else:
                    self._draw_continuation(painter, page_index + 1, len(chunks))
                self._draw_footer(painter, settings, page_index + 1, len(chunks))
            finally:
                painter.end()
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

    def _draw_statement_metadata(self, painter: QPainter, statement: dict) -> None:
        customer = statement.get("customer", {})
        values = (
            (31, 260, "العميل", customer.get("name", "—")),
            (260, 440, "كود العميل", customer.get("code", "—")),
            (440, 620, "الهاتف", customer.get("phone", "—")),
            (620, 820, "من تاريخ", statement.get("date_from", "—")),
            (820, 1020, "إلى تاريخ", statement.get("date_to", "—")),
        )
        for left, right, label, value in values:
            painter.fillRect(QRect(left, 350, right - left, 44), self.DARK_BLUE)
            painter.fillRect(QRect(left, 394, right - left, 44), self.WHITE)
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
        self._draw_text(
            painter,
            QRect(31, 446, 989, 42),
            f"رصيد أول المدة: {opening:,.2f} جنيه — "
            + ("كشف تفصيلي" if statement.get("detailed") else "كشف مختصر"),
            20,
            self.DARK_BLUE,
            bold=True,
            alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )

    def _draw_statement_rows(self, painter: QPainter, rows: list[dict]) -> None:
        header_top = 500
        body_top, body_bottom = 544, 1055
        for left, right, label, _ in self.COLUMNS:
            painter.fillRect(QRect(left, header_top, right - left, 44), self.DARK_BLUE)
            self._draw_text(
                painter,
                QRect(left + 2, header_top, right - left - 4, 44),
                label,
                15,
                self.WHITE,
                bold=True,
                min_size=10,
            )
        visible_rows = max(6, len(rows))
        row_height = (body_bottom - body_top) / visible_rows
        painter.fillRect(QRect(31, body_top, 989, body_bottom - body_top), self.WHITE)
        painter.setPen(QPen(self.GRID, 1))
        for left, _, _, _ in self.COLUMNS:
            painter.drawLine(left, body_top, left, body_bottom)
        painter.drawLine(1020, body_top, 1020, body_bottom)
        for row_index in range(visible_rows + 1):
            y = round(body_top + row_index * row_height)
            painter.drawLine(31, y, 1020, y)

        for row_index, row in enumerate(rows):
            top = round(body_top + row_index * row_height)
            bottom = round(body_top + (row_index + 1) * row_height)
            detail = bool(row.get("is_detail"))
            if detail:
                painter.fillRect(QRect(31, top, 989, bottom - top), self.WHITE)
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
                    QRect(left + 3, top + 1, right - left - 6, bottom - top - 2),
                    values[key],
                    13 if detail else 14,
                    self.BLACK,
                    bold=not detail,
                    min_size=8,
                )

    def _draw_statement_summary(self, painter: QPainter, statement: dict) -> None:
        summary = statement.get("summary", {})
        painter.fillRect(QRect(55, 1075, 920, 225), self.YELLOW)
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
        for index, (label, value) in enumerate(values):
            row = index // 2
            column = index % 2
            left = 75 + column * 450
            top = 1087 + row * 49
            self._draw_text(
                painter,
                QRect(left, top, 245, 40),
                label,
                15,
                self.BLACK,
                bold=True,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                min_size=11,
            )
            self._draw_text(
                painter,
                QRect(left + 250, top, 170, 40),
                f"{float(value or 0):,.2f}",
                18,
                self.DARK_BLUE,
                bold=True,
                min_size=12,
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
                        "document_number": "↳",
                        "document_type": "بند فاتورة",
                        "description": " — ".join(detail_parts),
                        "debit": 0,
                        "credit": 0,
                        "running_balance": movement.get("running_balance", 0),
                        "status": "",
                    }
                )
        return result


__all__ = ["CustomerStatementRenderer"]
