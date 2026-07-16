from __future__ import annotations

from PySide6.QtCore import QMarginsF, QRectF
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

from app.services.a4_document_renderer import A4DocumentRenderer


class A4PrintService:
    """Preview and print approved A4 sales documents with live data."""

    PRINT_DPI = 300
    MARGINS_MM = QMarginsF(5.0, 5.0, 5.0, 5.0)

    def __init__(self) -> None:
        self.renderer = A4DocumentRenderer()

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        self.preview_document(invoice, settings, parent)

    def preview_document(
        self,
        document: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        pages = self.renderer.render(document, settings)
        printer = self._create_printer(str(settings.get("printer_name", "")))
        self._apply_a4_layout(printer)

        preview = QPrintPreviewDialog(printer, parent)
        title = str(document.get("document_title") or "فاتورة مبيعات")
        number = str(document.get("invoice_number") or "")
        preview.setWindowTitle(f"معاينة {title} {number} — A4")
        preview.resize(1100, 850)
        preview.paintRequested.connect(
            lambda requested_printer: self._paint_pages(requested_printer, pages)
        )
        preview.exec()

    def _paint_pages(self, printer: QPrinter, pages: list[QImage]) -> None:
        self._apply_a4_layout(printer)
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("تعذر بدء طباعة مستند A4")

        try:
            target = QRectF(painter.viewport())
            for index, page in enumerate(pages):
                if index and not printer.newPage():
                    raise RuntimeError("تعذر إنشاء صفحة جديدة أثناء الطباعة")
                painter.drawImage(target, page)
        finally:
            painter.end()

    def _apply_a4_layout(self, printer: QPrinter) -> None:
        printer.setResolution(self.PRINT_DPI)
        layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            self.MARGINS_MM,
            QPageLayout.Unit.Millimeter,
        )
        printer.setPageLayout(layout)
        printer.setFullPage(False)

    @classmethod
    def _create_printer(cls, configured_name: str) -> QPrinter:
        configured = configured_name.strip().casefold()
        if configured:
            for printer_info in QPrinterInfo.availablePrinters():
                if printer_info.printerName().strip().casefold() == configured:
                    printer = QPrinter(
                        printer_info,
                        QPrinter.PrinterMode.HighResolution,
                    )
                    printer.setResolution(cls.PRINT_DPI)
                    return printer
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(cls.PRINT_DPI)
        return printer


__all__ = ["A4PrintService"]
