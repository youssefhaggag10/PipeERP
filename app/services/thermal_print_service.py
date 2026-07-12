from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, QTimer, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QTextDocument
from PySide6.QtPrintSupport import (
    QPrinter,
    QPrinterInfo,
    QPrintPreviewDialog,
    QPrintPreviewWidget,
)
from PySide6.QtWidgets import QWidget

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    PAPER_WIDTH_MM = 80.0
    PRINTABLE_WIDTH_MM = 72.0
    SIDE_MARGIN_MM = 4.0
    TOP_MARGIN_MM = 3.0
    BOTTOM_MARGIN_MM = 4.0
    HEIGHT_ALLOWANCE_MM = 6.0
    MIN_RECEIPT_HEIGHT_MM = 120.0
    PRINTER_DPI = 203

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        document = self._build_document(invoice, settings)
        receipt_height_mm = self._measure_receipt_height(document)
        printer = self._create_printer(str(settings.get("printer_name", "")))
        self._apply_page_layout(printer, receipt_height_mm)

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(
            f"معاينة فاتورة {invoice['invoice_number']} — رول 80 مم"
        )
        preview.resize(1000, 820)
        preview.paintRequested.connect(
            lambda requested_printer: self._paint_document(
                requested_printer,
                document,
                receipt_height_mm,
            )
        )

        preview_widget = preview.findChild(QPrintPreviewWidget)
        if preview_widget is not None:
            QTimer.singleShot(
                0,
                lambda: preview_widget.setZoomMode(
                    QPrintPreviewWidget.ZoomMode.FitInView
                ),
            )

        preview.exec()

    def _build_document(
        self,
        invoice: dict,
        settings: dict[str, str],
    ) -> QTextDocument:
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

    def _measure_receipt_height(self, document: QTextDocument) -> float:
        printable_width_points = self.PRINTABLE_WIDTH_MM * 72.0 / 25.4
        document.setPageSize(QSizeF(printable_width_points, 100000.0))
        document.setTextWidth(printable_width_points)

        content_height_points = max(
            1.0,
            float(document.documentLayout().documentSize().height()),
        )
        document.setPageSize(
            QSizeF(printable_width_points, content_height_points)
        )

        content_height_mm = content_height_points * 25.4 / 72.0
        return max(
            self.MIN_RECEIPT_HEIGHT_MM,
            content_height_mm
            + self.TOP_MARGIN_MM
            + self.BOTTOM_MARGIN_MM
            + self.HEIGHT_ALLOWANCE_MM,
        )

    def _paint_document(
        self,
        printer: QPrinter,
        document: QTextDocument,
        receipt_height_mm: float,
    ) -> None:
        self._apply_page_layout(printer, receipt_height_mm)

        printable_width_points = self.PRINTABLE_WIDTH_MM * 72.0 / 25.4
        document.setTextWidth(printable_width_points)
        content_height_points = max(
            1.0,
            float(document.documentLayout().documentSize().height()),
        )
        document.setPageSize(
            QSizeF(printable_width_points, content_height_points)
        )

        painter = QPainter()
        if not painter.begin(printer):
            return

        try:
            dpi_x = max(72, painter.device().logicalDpiX())
            dpi_y = max(72, painter.device().logicalDpiY())
            painter.scale(dpi_x / 72.0, dpi_y / 72.0)

            side_margin_points = self.SIDE_MARGIN_MM * 72.0 / 25.4
            top_margin_points = self.TOP_MARGIN_MM * 72.0 / 25.4
            painter.translate(side_margin_points, top_margin_points)

            document.drawContents(
                painter,
                QRectF(
                    0.0,
                    0.0,
                    printable_width_points,
                    content_height_points,
                ),
            )
        finally:
            painter.end()

    def _apply_page_layout(
        self,
        printer: QPrinter,
        receipt_height_mm: float,
    ) -> None:
        printer.setResolution(self.PRINTER_DPI)
        page_size = QPageSize(
            QSizeF(self.PAPER_WIDTH_MM, receipt_height_mm),
            QPageSize.Unit.Millimeter,
            "PipeERP-80mm-dynamic",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        page_layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,
            QMarginsF(0.0, 0.0, 0.0, 0.0),
            QPageLayout.Unit.Millimeter,
        )
        if not printer.setPageLayout(page_layout):
            printer.setPageSize(page_size)
            printer.setPageMargins(
                QMarginsF(0.0, 0.0, 0.0, 0.0),
                QPageLayout.Unit.Millimeter,
            )
        printer.setFullPage(True)

    def _create_printer(self, configured_name: str) -> QPrinter:
        configured = configured_name.strip().casefold()
        if configured:
            for printer_info in QPrinterInfo.availablePrinters():
                if printer_info.printerName().strip().casefold() == configured:
                    printer = QPrinter(
                        printer_info,
                        QPrinter.PrinterMode.HighResolution,
                    )
                    printer.setResolution(self.PRINTER_DPI)
                    return printer

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(self.PRINTER_DPI)
        return printer

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
                if (
                    color.alpha() > 10
                    and min(color.red(), color.green(), color.blue()) < 245
                ):
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
