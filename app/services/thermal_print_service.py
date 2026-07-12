from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, QTimer, QUrl
from PySide6.QtGui import (
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QTextDocument,
    QTextOption,
)
from PySide6.QtPrintSupport import (
    QPrinter,
    QPrinterInfo,
    QPrintPreviewDialog,
    QPrintPreviewWidget,
)
from PySide6.QtWidgets import QWidget

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    """Render and print an 80 mm receipt consistently on Linux and Windows.

    Qt preview and physical printer paint devices do not necessarily expose the
    same DPI or paper width.  The receipt is therefore rendered once to a 203
    DPI image, then that exact image is fitted to the printer's real page.
    """

    ROLL_WIDTH_MM = 80.0
    MAX_PRINTABLE_WIDTH_MM = 72.0
    MIN_THERMAL_WIDTH_MM = 50.0
    MAX_THERMAL_WIDTH_MM = 90.0
    MIN_SIDE_MARGIN_MM = 1.5
    TOP_MARGIN_MM = 2.5
    BOTTOM_MARGIN_MM = 4.0
    MIN_RECEIPT_HEIGHT_MM = 120.0
    RENDER_DPI = 203

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        printer = self._create_printer(str(settings.get("printer_name", "")))
        paper_width_mm = self._thermal_page_width_mm(printer)
        content_width_mm = self._content_width_mm(paper_width_mm)
        document = self._build_document(invoice, settings)
        receipt_image = self._render_receipt_image(document, content_width_mm)
        receipt_height_mm = max(
            self.MIN_RECEIPT_HEIGHT_MM,
            self.TOP_MARGIN_MM + self._pixels_to_mm(receipt_image.height()) + self.BOTTOM_MARGIN_MM,
        )
        self._apply_page_layout(printer, paper_width_mm, receipt_height_mm)

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(f"معاينة فاتورة {invoice['invoice_number']} — رول 80 مم")
        preview.resize(1000, 820)
        preview.paintRequested.connect(
            lambda requested_printer: self._paint_receipt_image(
                requested_printer,
                receipt_image,
                paper_width_mm,
                receipt_height_mm,
            )
        )

        preview_widget = preview.findChild(QPrintPreviewWidget)
        if preview_widget is not None:
            QTimer.singleShot(
                0,
                lambda: preview_widget.setZoomMode(QPrintPreviewWidget.ZoomMode.FitInView),
            )

        preview.exec()

    def _build_document(
        self,
        invoice: dict,
        settings: dict[str, str],
    ) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
        text_option = document.defaultTextOption()
        text_option.setUseDesignMetrics(True)
        text_option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        document.setDefaultTextOption(text_option)

        logo_url = self._add_image_resource(
            document,
            settings.get("logo_path", ""),
            "receipt:logo",
            trim_white=True,
        )
        qr_url = self._add_image_resource(
            document,
            settings.get("qr_path", ""),
            "receipt:instapay-qr",
            trim_white=True,
        )
        document.setHtml(
            build_sales_receipt_html(
                invoice,
                settings,
                logo_url=logo_url,
                qr_url=qr_url,
            )
        )
        return document

    def _render_receipt_image(
        self,
        document: QTextDocument,
        content_width_mm: float,
    ) -> QImage:
        width_points = self._mm_to_points(content_width_mm)
        document.setTextWidth(width_points)
        document.setPageSize(QSizeF(width_points, 100000.0))
        height_points = max(
            1.0,
            float(document.documentLayout().documentSize().height()),
        )
        document.setPageSize(QSizeF(width_points, height_points))

        width_pixels = max(1, self._mm_to_pixels(content_width_mm))
        height_pixels = max(
            1,
            int(math.ceil(height_points * self.RENDER_DPI / 72.0)),
        )
        image = QImage(width_pixels, height_pixels, QImage.Format.Format_RGB32)
        image.fill(0xFFFFFFFF)
        dots_per_meter = round(self.RENDER_DPI / 0.0254)
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)

        painter = QPainter(image)
        try:
            painter.scale(self.RENDER_DPI / 72.0, self.RENDER_DPI / 72.0)
            document.drawContents(
                painter,
                QRectF(0.0, 0.0, width_points, height_points),
            )
        finally:
            painter.end()
        return image

    def _paint_receipt_image(
        self,
        printer: QPrinter,
        receipt_image: QImage,
        requested_paper_width_mm: float,
        receipt_height_mm: float,
    ) -> None:
        self._apply_page_layout(
            printer,
            requested_paper_width_mm,
            receipt_height_mm,
        )

        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("تعذر بدء الطباعة. راجع اتصال الطابعة والدرايفر.")

        try:
            viewport = QRectF(painter.viewport())
            actual_width_mm = self._page_width_mm(printer)
            if actual_width_mm <= 0.0:
                actual_width_mm = requested_paper_width_mm

            pixels_per_mm = viewport.width() / actual_width_mm
            content_width_mm = self._content_width_mm(actual_width_mm)
            target_width = min(
                viewport.width(),
                content_width_mm * pixels_per_mm,
            )
            scale = target_width / max(1, receipt_image.width())
            target_height = receipt_image.height() * scale
            left = viewport.left() + (viewport.width() - target_width) / 2.0
            top = viewport.top() + self.TOP_MARGIN_MM * pixels_per_mm

            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
            painter.drawImage(
                QRectF(left, top, target_width, target_height),
                receipt_image,
            )
        finally:
            painter.end()

    def _apply_page_layout(
        self,
        printer: QPrinter,
        paper_width_mm: float,
        receipt_height_mm: float,
    ) -> bool:
        printer.setResolution(self.RENDER_DPI)
        page_size = QPageSize(
            QSizeF(paper_width_mm, receipt_height_mm),
            QPageSize.Unit.Millimeter,
            "PipeERP-thermal-receipt",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        page_layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,
            QMarginsF(0.0, 0.0, 0.0, 0.0),
            QPageLayout.Unit.Millimeter,
        )
        accepted = bool(printer.setPageLayout(page_layout))
        if not accepted:
            size_accepted = bool(printer.setPageSize(page_size))
            margins_accepted = bool(
                printer.setPageMargins(
                    QMarginsF(0.0, 0.0, 0.0, 0.0),
                    QPageLayout.Unit.Millimeter,
                )
            )
            accepted = size_accepted and margins_accepted
        printer.setFullPage(True)
        return accepted

    def _create_printer(self, configured_name: str) -> QPrinter:
        configured = configured_name.strip().casefold()
        if configured:
            for printer_info in QPrinterInfo.availablePrinters():
                if printer_info.printerName().strip().casefold() == configured:
                    printer = QPrinter(
                        printer_info,
                        QPrinter.PrinterMode.HighResolution,
                    )
                    printer.setResolution(self.RENDER_DPI)
                    return printer

            raise ValueError(
                "الطابعة المحفوظة غير موجودة حاليًا. اختر اسم الطابعة الصحيح من إعدادات الطباعة."
            )

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(self.RENDER_DPI)
        return printer

    def _thermal_page_width_mm(self, printer: QPrinter) -> float:
        width_mm = self._page_width_mm(printer)
        if self.MIN_THERMAL_WIDTH_MM <= width_mm <= self.MAX_THERMAL_WIDTH_MM:
            return width_mm
        return self.ROLL_WIDTH_MM

    @classmethod
    def _content_width_mm(cls, page_width_mm: float) -> float:
        available_width = max(
            1.0,
            page_width_mm - (2.0 * cls.MIN_SIDE_MARGIN_MM),
        )
        return min(cls.MAX_PRINTABLE_WIDTH_MM, available_width)

    @staticmethod
    def _page_width_mm(printer: QPrinter) -> float:
        rect = printer.pageLayout().fullRect(QPageLayout.Unit.Millimeter)
        return float(rect.width())

    @classmethod
    def _mm_to_pixels(cls, value: float) -> int:
        return round(value * cls.RENDER_DPI / 25.4)

    @staticmethod
    def _mm_to_points(value: float) -> float:
        return value * 72.0 / 25.4

    @classmethod
    def _pixels_to_mm(cls, value: int) -> float:
        return value * 25.4 / cls.RENDER_DPI

    @staticmethod
    def _add_image_resource(
        document: QTextDocument,
        path_value: object,
        resource_name: str,
        *,
        trim_white: bool = False,
    ) -> str:
        path = Path(str(path_value or ""))
        if not path.is_file():
            return ""

        image = QImage(str(path))
        if image.isNull():
            return ""
        if trim_white:
            image = ThermalPrintService._trim_white_border(image)

        url = QUrl(resource_name)
        document.addResource(
            QTextDocument.ResourceType.ImageResource,
            url,
            image,
        )
        return resource_name

    @staticmethod
    def _trim_white_border(image: QImage) -> QImage:
        width = image.width()
        height = image.height()
        step = max(1, min(width, height) // 320)
        left, top, right, bottom = width, height, -1, -1

        for y in range(0, height, step):
            for x in range(0, width, step):
                color = image.pixelColor(x, y)
                if color.alpha() > 10 and min(color.red(), color.green(), color.blue()) < 245:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)

        if right < left or bottom < top:
            return image

        padding = max(4, min(width, height) // 100)
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(width - 1, right + padding)
        bottom = min(height - 1, bottom + padding)
        return image.copy(left, top, right - left + 1, bottom - top + 1)


__all__ = ["ThermalPrintService"]
