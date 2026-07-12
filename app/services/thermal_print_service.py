from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    PAPER_WIDTH_MM = 80.0

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        printer = self._printer(settings.get("printer_name", ""))

        # Start with a tall page only to establish the real 80 mm printable width.
        # The final page height is measured from the rendered document below.
        measuring_page = QPageSize(
            QSizeF(self.PAPER_WIDTH_MM, 500.0),
            QPageSize.Unit.Millimeter,
            "PipeERP-80mm-measure",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        printer.setPageSize(measuring_page)
        printer.setPageMargins(
            QMarginsF(4.0, 3.0, 4.0, 3.0),
            QPageLayout.Unit.Millimeter,
        )
        printer.setFullPage(False)

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

        printable_width_points = printer.pageLayout().paintRect(
            QPageLayout.Unit.Point
        ).width()
        document.setTextWidth(printable_width_points)
        content_height_points = document.documentLayout().documentSize().height()
        content_height_mm = content_height_points * 25.4 / 72.0
        receipt_height_mm = max(120.0, content_height_mm + 10.0)

        final_page = QPageSize(
            QSizeF(self.PAPER_WIDTH_MM, receipt_height_mm),
            QPageSize.Unit.Millimeter,
            "PipeERP-80mm",
            QPageSize.SizeMatchPolicy.ExactMatch,
        )
        printer.setPageSize(final_page)
        document.setPageSize(
            printer.pageLayout().paintRect(QPageLayout.Unit.Point).size()
        )

        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(f"معاينة فاتورة {invoice['invoice_number']} — 80mm")
        preview.resize(900, 760)
        preview.paintRequested.connect(document.print_)
        preview.exec()

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
