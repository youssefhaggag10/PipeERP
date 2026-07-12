from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    PAPER_WIDTH_MM = 80.0
    SIDE_MARGIN_MM = 4.0
    TOP_MARGIN_MM = 3.0
    BOTTOM_MARGIN_MM = 3.0
    MEASURING_HEIGHT_MM = 500.0
    MIN_RECEIPT_HEIGHT_MM = 120.0
    HEIGHT_ALLOWANCE_MM = 8.0

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        printer = self._printer(settings.get("printer_name", ""))
        document = self._document(invoice, settings)

        # Build the first preview using the exact printable width of an 80 mm roll.
        self._prepare_document(printer, document)

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(f"معاينة فاتورة {invoice['invoice_number']} — 80mm")
        preview.resize(900, 760)

        # The native print dialog can reset a custom roll to the driver's default paper.
        # Reapply the measured 80 mm layout every time Qt requests painting, including
        # the final physical print, so the driver cannot compress the receipt vertically.
        preview.paintRequested.connect(
            lambda requested_printer: self._render_document(requested_printer, document)
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

    def _render_document(self, printer: QPrinter, document: QTextDocument) -> None:
        self._prepare_document(printer, document)
        document.print_(printer)

    def _prepare_document(self, printer: QPrinter, document: QTextDocument) -> float:
        printable_width_mm = self.PAPER_WIDTH_MM - (self.SIDE_MARGIN_MM * 2)
        printable_width_points = printable_width_mm * 72.0 / 25.4

        # Measure independently from the active printer driver. Some thermal drivers
        # report A4 or a short label after the print dialog and would otherwise make
        # QTextDocument shrink the complete receipt to that reported page.
        document.setPageSize(QSizeF())
        document.setTextWidth(printable_width_points)
        content_height_points = document.documentLayout().documentSize().height()
        content_height_mm = content_height_points * 25.4 / 72.0
        receipt_height_mm = max(
            self.MIN_RECEIPT_HEIGHT_MM,
            content_height_mm + self.HEIGHT_ALLOWANCE_MM,
        )

        self._apply_page_layout(printer, receipt_height_mm)

        printable_height_mm = max(
            1.0,
            receipt_height_mm - self.TOP_MARGIN_MM - self.BOTTOM_MARGIN_MM,
        )
        document.setPageSize(
            QSizeF(
                printable_width_points,
                printable_height_mm * 72.0 / 25.4,
            )
        )
        return receipt_height_mm

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
