from pathlib import Path

from PySide6.QtCore import QMarginsF, QSizeF, Qt, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QTextDocument
from PySide6.QtPrintSupport import (
    QPrintDialog,
    QPrinter,
    QPrinterInfo,
    QPrintPreviewWidget,
)
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    PAPER_WIDTH_MM = 80.0
    MEASURING_HEIGHT_MM = 500.0
    SIDE_MARGIN_MM = 4.0
    TOP_MARGIN_MM = 3.0
    BOTTOM_MARGIN_MM = 3.0
    MIN_RECEIPT_HEIGHT_MM = 120.0
    HEIGHT_ALLOWANCE_MM = 10.0

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        printer = self._printer(settings.get("printer_name", ""))
        document = self._document(invoice, settings)

        # Prepare the initial preview geometry. The same geometry is applied again after
        # the native print dialog closes because Windows printer drivers may reset custom
        # roll dimensions when the selected printer changes.
        self._prepare_document(printer, document)

        dialog = QDialog(parent)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setWindowTitle(f"معاينة فاتورة {invoice['invoice_number']} — 80mm")
        dialog.resize(900, 760)

        preview = QPrintPreviewWidget(printer, dialog)
        preview.setZoomMode(QPrintPreviewWidget.ZoomMode.FitToWidth)
        preview.paintRequested.connect(
            lambda requested_printer: self._render_document(requested_printer, document)
        )

        print_button = QPushButton("طباعة الفاتورة")
        print_button.setDefault(True)
        print_button.clicked.connect(
            lambda: self._show_print_dialog(printer, document, dialog)
        )
        close_button = QPushButton("إغلاق")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(dialog.reject)

        actions = QHBoxLayout()
        actions.addStretch()
        actions.addWidget(close_button)
        actions.addWidget(print_button)

        layout = QVBoxLayout(dialog)
        layout.addWidget(preview)
        layout.addLayout(actions)

        preview.updatePreview()
        dialog.exec()

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

    def _show_print_dialog(
        self,
        printer: QPrinter,
        document: QTextDocument,
        parent: QWidget,
    ) -> None:
        print_dialog = QPrintDialog(printer, parent)
        print_dialog.setWindowTitle("اختيار الطابعة — فاتورة 80mm")
        if print_dialog.exec() != QDialog.DialogCode.Accepted:
            return

        # QPrintDialog can replace the page layout with the driver's default. Reapply the
        # measured 80 mm roll immediately before painting to keep print and preview equal.
        self._render_document(printer, document)

    def _render_document(self, printer: QPrinter, document: QTextDocument) -> None:
        self._prepare_document(printer, document)
        document.print_(printer)

    def _prepare_document(self, printer: QPrinter, document: QTextDocument) -> float:
        self._apply_page_layout(printer, self.MEASURING_HEIGHT_MM, measuring=True)

        printable_width_points = printer.pageLayout().paintRect(
            QPageLayout.Unit.Point
        ).width()
        document.setTextWidth(printable_width_points)
        content_height_points = document.documentLayout().documentSize().height()
        receipt_height_mm = max(
            self.MIN_RECEIPT_HEIGHT_MM,
            content_height_points * 25.4 / 72.0 + self.HEIGHT_ALLOWANCE_MM,
        )

        self._apply_page_layout(printer, receipt_height_mm)
        final_paint_rect = printer.pageLayout().paintRect(QPageLayout.Unit.Point)

        # Some drivers clamp margins or custom width. If that happens, measure once more
        # using the actual accepted width before locking the final page height.
        if abs(final_paint_rect.width() - printable_width_points) > 0.5:
            document.setTextWidth(final_paint_rect.width())
            content_height_points = document.documentLayout().documentSize().height()
            receipt_height_mm = max(
                self.MIN_RECEIPT_HEIGHT_MM,
                content_height_points * 25.4 / 72.0 + self.HEIGHT_ALLOWANCE_MM,
            )
            self._apply_page_layout(printer, receipt_height_mm)
            final_paint_rect = printer.pageLayout().paintRect(QPageLayout.Unit.Point)

        document.setPageSize(final_paint_rect.size())
        return receipt_height_mm

    def _apply_page_layout(
        self,
        printer: QPrinter,
        height_mm: float,
        *,
        measuring: bool = False,
    ) -> None:
        page_name = "PipeERP-80mm-measure" if measuring else "PipeERP-80mm"
        page_size = QPageSize(
            QSizeF(self.PAPER_WIDTH_MM, height_mm),
            QPageSize.Unit.Millimeter,
            page_name,
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
