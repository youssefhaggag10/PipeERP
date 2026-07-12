from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, QUrl
from PySide6.QtGui import (
    QImage,
    QPageLayout,
    QPageSize,
    QPainter,
    QTextDocument,
)
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    """Render and print 80 mm receipts without driver-controlled vertical scaling.

    QTextDocument.print_() lets the printer driver fit the document to whatever page
    size it reports. Several thermal drivers report a short label during the physical
    print even though the preview uses the custom roll size, which compresses the whole
    invoice vertically. The receipt is therefore rasterized once at the printer's native
    203 dpi aspect ratio and painted at an explicit physical size.
    """

    PAPER_WIDTH_MM = 80.0
    SIDE_MARGIN_MM = 4.0
    TOP_MARGIN_MM = 3.0
    BOTTOM_MARGIN_MM = 3.0
    MIN_RECEIPT_HEIGHT_MM = 120.0
    HEIGHT_ALLOWANCE_MM = 8.0
    RASTER_DPI = 203

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        printer = self._printer(settings.get("printer_name", ""))
        document = self._document(invoice, settings)
        receipt_image, content_height_mm = self._render_receipt_image(document)
        receipt_height_mm = max(
            self.MIN_RECEIPT_HEIGHT_MM,
            content_height_mm
            + self.TOP_MARGIN_MM
            + self.BOTTOM_MARGIN_MM
            + self.HEIGHT_ALLOWANCE_MM,
        )
        self._apply_page_layout(printer, receipt_height_mm)

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(f"معاينة فاتورة {invoice['invoice_number']} — 80mm")
        preview.resize(900, 760)
        preview.paintRequested.connect(
            lambda requested_printer: self._paint_receipt(
                requested_printer,
                receipt_image,
                content_height_mm,
                receipt_height_mm,
            )
        )
        preview.exec()

    def _document(self, invoice: dict, settings: dict[str, str]) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
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

    def _render_receipt_image(self, document: QTextDocument) -> tuple[QImage, float]:
        printable_width_mm = self.PAPER_WIDTH_MM - (self.SIDE_MARGIN_MM * 2)
        printable_width_points = printable_width_mm * 72.0 / 25.4

        # Give the document an effectively unlimited height while measuring. This keeps
        # the preview layout intact and prevents automatic pagination or fit-to-page.
        document.setPageSize(QSizeF(printable_width_points, 100000.0))
        document.setTextWidth(printable_width_points)
        document.adjustSize()

        document_size = document.documentLayout().documentSize()
        content_height_points = max(1.0, float(document_size.height()))
        content_height_mm = content_height_points * 25.4 / 72.0

        scale = self.RASTER_DPI / 72.0
        image_width = max(1, math.ceil(printable_width_points * scale))
        image_height = max(1, math.ceil(content_height_points * scale))
        image = QImage(
            image_width,
            image_height,
            QImage.Format.Format_ARGB32_Premultiplied,
        )
        image.fill(0xFFFFFFFF)
        dots_per_meter = round(self.RASTER_DPI / 0.0254)
        image.setDotsPerMeterX(dots_per_meter)
        image.setDotsPerMeterY(dots_per_meter)

        painter = QPainter(image)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            painter.scale(scale, scale)
            document.drawContents(
                painter,
                QRectF(0.0, 0.0, printable_width_points, content_height_points),
            )
        finally:
            painter.end()

        return image, content_height_mm

    def _paint_receipt(
        self,
        printer: QPrinter,
        image: QImage,
        content_height_mm: float,
        receipt_height_mm: float,
    ) -> None:
        # The native print dialog may replace the custom roll with the driver's default.
        # Apply the 80 mm page again immediately before starting the painter.
        self._apply_page_layout(printer, receipt_height_mm)

        resolution = max(72, int(printer.resolution()))
        printable_width_mm = self.PAPER_WIDTH_MM - (self.SIDE_MARGIN_MM * 2)
        target_width_px = printable_width_mm * resolution / 25.4
        target_height_px = content_height_mm * resolution / 25.4

        paint_rect = printer.pageLayout().paintRectPixels(resolution)
        target = QRectF(
            float(paint_rect.x()),
            float(paint_rect.y()),
            float(target_width_px),
            float(target_height_px),
        )

        painter = QPainter()
        if not painter.begin(printer):
            return
        try:
            # Explicit target dimensions preserve the physical 80 mm receipt ratio.
            # No fit-to-page or page-height scaling is delegated to QTextDocument.
            painter.drawImage(target, image, QRectF(image.rect()))
        finally:
            painter.end()

    def _apply_page_layout(self, printer: QPrinter, receipt_height_mm: float) -> None:
        page_size = QPageSize(
            QSizeF(self.PAPER_WIDTH_MM, receipt_height_mm),
            QPageSize.Unit.Millimeter,
            "PipeERP-80mm",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        margins = QMarginsF(
            self.SIDE_MARGIN_MM,
            self.TOP_MARGIN_MM,
            self.SIDE_MARGIN_MM,
            self.BOTTOM_MARGIN_MM,
        )
        page_layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,
            margins,
            QPageLayout.Unit.Millimeter,
        )
        if not printer.setPageLayout(page_layout):
            printer.setPageSize(page_size)
            printer.setPageMargins(margins, QPageLayout.Unit.Millimeter)
        printer.setFullPage(False)

    @staticmethod
    def _printer(configured_name: str) -> QPrinter:
        configured = configured_name.strip().casefold()
        for printer_info in QPrinterInfo.availablePrinters():
            if configured and configured in printer_info.printerName().casefold():
                return QPrinter(printer_info, QPrinter.PrinterMode.HighResolution)
        return QPrinter(QPrinter.PrinterMode.HighResolution)

    @staticmethod
    def _add_image_resource(
        document: QTextDocument,
        path_value: str,
        resource_name: str,
        *,
        trim_white: bool = False,
    ) -> str:
        path = Path(path_value)
        if not path.is_file():
            return ""
        image = QImage(str(path))
        if image.isNull():
            return ""
        if trim_white:
            image = ThermalPrintService._trim_white_border(image)
        url = QUrl(resource_name)
        document.addResource(QTextDocument.ResourceType.ImageResource, url, image)
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
