from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QTextDocument, QTextOption
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

from app.services.a4_invoice_template_service import build_sales_invoice_a4_html


class A4PrintService:
    """Preview and print a standard A4 sales invoice on Linux and Windows."""

    MARGINS_MM = QMarginsF(9.0, 8.0, 9.0, 8.0)

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        document = self._build_document(invoice, settings)
        printer = self._create_printer(str(settings.get("printer_name", "")))
        self._apply_a4_layout(printer)

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(f"معاينة فاتورة مبيعات {invoice['invoice_number']} — A4")
        preview.resize(1100, 850)
        preview.paintRequested.connect(
            lambda requested_printer: self._print_document(requested_printer, document)
        )
        preview.exec()

    def _build_document(self, invoice: dict, settings: dict[str, str]) -> QTextDocument:
        document = QTextDocument()
        document.setDocumentMargin(0)
        option = document.defaultTextOption()
        option.setUseDesignMetrics(True)
        option.setWrapMode(QTextOption.WrapMode.WordWrap)
        document.setDefaultTextOption(option)

        logo_url = self._add_image_resource(
            document,
            settings.get("logo_path", ""),
            "invoice:logo",
            trim_white=True,
        )
        qr_url = self._add_image_resource(
            document,
            settings.get("qr_path", ""),
            "invoice:instapay-qr",
            trim_white=True,
        )
        document.setHtml(
            build_sales_invoice_a4_html(
                invoice,
                settings,
                logo_url=logo_url,
                qr_url=qr_url,
            )
        )
        return document

    def _print_document(self, printer: QPrinter, document: QTextDocument) -> None:
        self._apply_a4_layout(printer)
        document.print_(printer)

    def _apply_a4_layout(self, printer: QPrinter) -> None:
        layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            self.MARGINS_MM,
            QPageLayout.Unit.Millimeter,
        )
        printer.setPageLayout(layout)
        printer.setFullPage(False)

    @staticmethod
    def _create_printer(configured_name: str) -> QPrinter:
        configured = configured_name.strip().casefold()
        if configured:
            for printer_info in QPrinterInfo.availablePrinters():
                if printer_info.printerName().strip().casefold() == configured:
                    return QPrinter(printer_info, QPrinter.PrinterMode.HighResolution)
        return QPrinter(QPrinter.PrinterMode.HighResolution)

    @staticmethod
    def _add_image_resource(
        document: QTextDocument,
        path_value: object,
        resource_name: str,
        *,
        trim_white: bool,
    ) -> str:
        path = Path(str(path_value or ""))
        if not path.is_file():
            return ""
        image = QImage(str(path))
        if image.isNull():
            return ""
        if trim_white:
            image = A4PrintService._trim_white_border(image)
        url = QUrl(resource_name)
        document.addResource(QTextDocument.ResourceType.ImageResource, url, image)
        return resource_name

    @staticmethod
    def _trim_white_border(image: QImage) -> QImage:
        width, height = image.width(), image.height()
        left, top, right, bottom = width, height, -1, -1
        step = max(1, min(width, height) // 320)
        for y in range(0, height, step):
            for x in range(0, width, step):
                color = image.pixelColor(x, y)
                if color.alpha() > 10 and min(color.red(), color.green(), color.blue()) < 245:
                    left, top = min(left, x), min(top, y)
                    right, bottom = max(right, x), max(bottom, y)
        if right < left or bottom < top:
            return image
        padding = max(4, min(width, height) // 100)
        left, top = max(0, left - padding), max(0, top - padding)
        right, bottom = min(width - 1, right + padding), min(height - 1, bottom + padding)
        return image.copy(left, top, right - left + 1, bottom - top + 1)


__all__ = ["A4PrintService"]
