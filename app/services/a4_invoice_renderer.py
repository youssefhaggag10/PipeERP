from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPen

from app.core.config import AppConfig
from app.utils.datetime_utils import format_egypt_datetime
from app.utils.print_phone_utils import footer_phone_text


class A4InvoiceRenderer:
    """Place live invoice data over the approved A4 visual design."""

    BLUE = QColor("#074b98")
    DARK_BLUE = QColor("#063f82")
    YELLOW = QColor("#f7bf00")
    RED = QColor("#d70f18")
    GREEN = QColor("#087520")
    BLACK = QColor("#111111")
    WHITE = QColor("#ffffff")
    GRID = QColor("#68727e")
    FONT_FAMILY = "DejaVu Sans"
    ROWS_PER_PAGE = 6
    OUTPUT_SCALE = 2

    META_COLUMNS = (
        (31, 183, "طريقة الدفع", "payment_methods"),
        (183, 302, "الهاتف", "customer_phone"),
        (302, 437, "العميل", "customer_name"),
        (437, 565, "الوقت", "invoice_time"),
        (565, 715, "التاريخ", "invoice_date"),
        (715, 863, "رقم الأمر", "order_number"),
        (863, 1021, "رقم الفاتورة", "invoice_number"),
    )
    ITEM_COLUMNS = (
        (31, 207, "ملاحظات", "notes"),
        (207, 351, "الإجمالي", "line_total"),
        (351, 496, "سعر الوحدة", "unit_price"),
        (496, 616, "الكمية", "quantity"),
        (616, 741, "الوحدة", "unit"),
        (741, 955, "البيان", "name"),
        (955, 1020, "م", "serial"),
    )
    TERMS = (
        "السعر يشمل جودة المنتج وضمان جودة الإنتاج ودقة وسرعة التوريد والتسليم.",
        "الأسعار غير شاملة النقل، ومتاح النقل في جميع أنحاء الجمهورية وخارجها.",
        "يتم دفع 50% والباقي عند الاستلام.",
        "متوفر جميع الأقطار من 25 مم إلى 800 مم.",
        "متوفر جميع الضغوطات (4 بار، 6 بار، 10 بار).",
        "تخضع جميع المنتجات للاختبارات اللازمة لضمان أعلى جودة قبل الوصول للعميل.",
    )

    def __init__(self, background_path: str | Path | None = None) -> None:
        self.background_path = Path(background_path or self.default_background_path())

    @staticmethod
    def default_background_path() -> Path:
        return AppConfig.project_root() / "app" / "assets" / "print" / "a4_invoice_background.png"

    def render(self, invoice: dict, settings: dict[str, str]) -> list[QImage]:
        source = QImage(str(self.background_path))
        if source.isNull():
            raise ValueError("تعذر تحميل تصميم فاتورة A4")
        background = source.scaled(
            source.width() * self.OUTPUT_SCALE,
            source.height() * self.OUTPUT_SCALE,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        lines = list(invoice.get("lines", []))
        chunks = [
            lines[index : index + self.ROWS_PER_PAGE]
            for index in range(0, max(1, len(lines)), self.ROWS_PER_PAGE)
        ]
        if not chunks:
            chunks = [[]]

        pages = []
        for page_index, chunk in enumerate(chunks):
            page = background.copy()
            painter = QPainter(page)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.scale(self.OUTPUT_SCALE, self.OUTPUT_SCALE)
            try:
                self._draw_header(painter, settings)
                self._draw_metadata(painter, invoice)
                self._draw_items(
                    painter,
                    chunk,
                    serial_offset=page_index * self.ROWS_PER_PAGE,
                )
                if page_index == len(chunks) - 1:
                    self._draw_totals(painter, invoice)
                    self._draw_terms(painter)
                else:
                    self._draw_continuation(painter, page_index + 1, len(chunks))
                self._draw_footer(painter, settings, page_index + 1, len(chunks))
            finally:
                painter.end()
            pages.append(page)
        return pages

    def _draw_header(self, painter: QPainter, settings: dict[str, str]) -> None:
        company_ar, company_en = self._company_parts(settings.get("company_name"))
        self._draw_text(
            painter,
            QRect(300, 45, 555, 62),
            company_ar or "ثري إيه بايب",
            42,
            self.BLUE,
            bold=True,
        )
        self._draw_text(
            painter,
            QRect(300, 100, 555, 48),
            company_en or "3A FOR PLASTIC PRODUCTS",
            42,
            self.BLUE,
            bold=True,
            min_size=30,
        )
        self._draw_text(
            painter,
            QRect(310, 150, 535, 35),
            "لتصنيع المواسير ومنتجات البلاستيك",
            21,
            self.BLACK,
            bold=True,
        )
        self._draw_text(
            painter,
            QRect(255, 250, 545, 76),
            "فاتورة مبيعات",
            48,
            self.BLUE,
            bold=True,
        )

    def _draw_metadata(self, painter: QPainter, invoice: dict) -> None:
        date_value, time_value = self._date_parts(invoice.get("invoice_date"))
        values = dict(invoice)
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
            self._draw_text(
                painter,
                QRect(left + 5, 459, right - left - 10, 39),
                str(values.get(key, "") or "—"),
                16,
                self.BLACK,
                bold=True,
                min_size=11,
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
                QRect(left + 3, 522, right - left - 6, 52),
                label,
                18,
                self.WHITE if label != "م" else self.BLACK,
                bold=True,
                min_size=12,
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
                "unit_price": self._money(line.get("unit_price")),
                "quantity": f"{float(line.get('quantity', 0) or 0):g}",
                "unit": str(line.get("unit", "") or ""),
                "name": self._product_text(line),
                "serial": str(serial_offset + row_index + 1),
            }
            for left, right, _, key in self.ITEM_COLUMNS:
                self._draw_text(
                    painter,
                    QRect(left + 5, top + 3, right - left - 10, bottom - top - 6),
                    values[key],
                    17 if key not in {"name", "notes"} else 16,
                    self.BLACK,
                    bold=True,
                    min_size=10,
                )

    def _draw_totals(self, painter: QPainter, invoice: dict) -> None:
        total = f"الإجمالي: {self._money(invoice.get('total'))} جنيها"
        paid = f"تم دفع: {self._money(invoice.get('paid'))} جنيها"
        remaining = f"إجمالي المتبقي: {self._money(invoice.get('remaining'))} جنيها"
        self._draw_text(
            painter,
            QRect(70, 805, 875, 67),
            total,
            36,
            self.WHITE,
            bold=True,
        )
        self._draw_text(
            painter,
            QRect(70, 884, 875, 65),
            paid,
            34,
            self.RED,
            bold=True,
        )
        self._draw_text(
            painter,
            QRect(70, 962, 875, 61),
            remaining,
            32,
            self.GREEN,
            bold=True,
        )

    def _draw_terms(self, painter: QPainter) -> None:
        self._draw_text(
            painter,
            QRect(795, 1048, 218, 36),
            "الشروط والملاحظات",
            20,
            self.WHITE,
            bold=True,
        )
        self._draw_text(
            painter,
            QRect(45, 1190, 165, 80),
            "جودة مضمونة\nوثقة تدوم",
            23,
            self.BLACK,
            bold=True,
        )
        term_y = 1085
        for term in self.TERMS:
            self._draw_text(
                painter,
                QRect(215, term_y, 745, 32),
                term,
                19,
                self.BLACK,
                bold=True,
                alignment=Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                min_size=14,
            )
            term_y += 39

    def _draw_continuation(self, painter: QPainter, page: int, total_pages: int) -> None:
        self._draw_text(
            painter,
            QRect(70, 805, 875, 67),
            f"تابع الأصناف — صفحة {page} من {total_pages}",
            30,
            self.WHITE,
            bold=True,
        )

    def _draw_footer(
        self,
        painter: QPainter,
        settings: dict[str, str],
        page_number: int,
        total_pages: int,
    ) -> None:
        main_phone, sales_phones = footer_phone_text(settings.get("phones", ""))
        if main_phone:
            self._draw_text(
                painter,
                QRect(105, 1368, 245, 43),
                main_phone,
                26,
                self.WHITE,
                bold=True,
            )
        if sales_phones:
            self._draw_text(
                painter,
                QRect(100, 1406, 250, 50),
                sales_phones,
                16,
                self.YELLOW,
                bold=True,
                min_size=9,
            )

        company_ar, company_en = self._company_parts(settings.get("company_name"))
        self._draw_text(
            painter,
            QRect(500, 1362, 210, 46),
            company_ar or "ثري إيه بايب",
            27,
            self.WHITE,
            bold=True,
        )
        self._draw_text(
            painter,
            QRect(500, 1406, 210, 38),
            company_en or "3A FOR PLASTIC PRODUCTS",
            27,
            self.WHITE,
            bold=True,
            min_size=20,
        )
        self._draw_text(
            painter,
            QRect(735, 1370, 205, 70),
            str(settings.get("address", "") or "المنوفية - سرس الليان"),
            20,
            self.WHITE,
            bold=True,
            min_size=14,
        )
        if total_pages > 1:
            self._draw_text(
                painter,
                QRect(480, 1440, 220, 25),
                f"{page_number} / {total_pages}",
                12,
                self.WHITE,
                bold=False,
            )

    def _draw_text(
        self,
        painter: QPainter,
        rect: QRect,
        text: str,
        size: int,
        color: QColor,
        *,
        bold: bool,
        min_size: int = 9,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter,
    ) -> None:
        value = str(text or "")
        flags = int(alignment | Qt.TextFlag.TextWordWrap)
        font = self._fitted_font(value, rect, size, min_size, bold, flags)
        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(rect, flags, value)

    def _fitted_font(
        self,
        text: str,
        rect: QRect,
        size: int,
        min_size: int,
        bold: bool,
        flags: int,
    ) -> QFont:
        for candidate in range(size, min_size - 1, -1):
            font = QFont(self.FONT_FAMILY)
            font.setPixelSize(candidate)
            font.setBold(bold)
            bounds = QFontMetrics(font).boundingRect(rect, flags, text)
            if bounds.width() <= rect.width() and bounds.height() <= rect.height():
                return font
        font = QFont(self.FONT_FAMILY)
        font.setPixelSize(min_size)
        font.setBold(bold)
        return font

    @staticmethod
    def _date_parts(value: object) -> tuple[str, str]:
        formatted = format_egypt_datetime(value)
        if " " not in formatted:
            return formatted, ""
        date_value, time_value = formatted.split(" ", 1)
        return date_value, time_value

    @staticmethod
    def _company_parts(value: object) -> tuple[str, str]:
        text = str(value or "").strip()
        for separator in (" - ", " – ", " — "):
            if separator in text:
                arabic, english = text.split(separator, 1)
                return arabic.strip(), english.strip().upper()
        return text, ""

    @staticmethod
    def _money(value: object) -> str:
        return f"{float(value or 0):,.2f}"

    @staticmethod
    def _product_text(line: dict) -> str:
        name = str(line.get("name", "") or "")
        code = str(line.get("code", "") or "")
        return f"{name}\n{code}" if code else name


__all__ = ["A4InvoiceRenderer"]
