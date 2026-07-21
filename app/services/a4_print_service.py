from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewDialog
from PySide6.QtWidgets import QWidget

from app.services.a4_document_renderer import A4DocumentRenderer
from app.services.customer_statement_renderer import CustomerStatementRenderer
from app.services.weight_invoice_renderer import WeightInvoiceRenderer


class A4PrintService:
    """Preview, export and print approved A4 business documents."""

    PRINT_DPI = 300
    MARGINS_MM = QMarginsF(5.0, 5.0, 5.0, 5.0)

    def __init__(self) -> None:
        self.renderer = A4DocumentRenderer()
        self.weight_renderer = WeightInvoiceRenderer()
        self.statement_renderer = CustomerStatementRenderer()

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        self.preview_document(invoice, settings, parent)

    def preview_weight_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        pages = self.weight_renderer.render(invoice, settings)
        self._preview_pages(
            pages,
            title=f"معاينة فاتورة وزن {invoice.get('invoice_number', '')} — A4",
            settings=settings,
            parent=parent,
        )

    def preview_customer_statement(
        self,
        statement: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        pages = self.statement_renderer.render(statement, settings)
        customer_name = statement.get("customer", {}).get("name", "")
        self._preview_pages(
            pages,
            title=f"معاينة كشف حساب {customer_name} — A4",
            settings=settings,
            parent=parent,
        )

    def preview_document(
        self,
        document: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        pages = self.renderer.render(document, settings)
        title = str(document.get("document_title") or "فاتورة مبيعات")
        number = str(document.get("invoice_number") or "")
        self._preview_pages(
            pages,
            title=f"معاينة {title} {number} — A4",
            settings=settings,
            parent=parent,
        )

    def export_weight_invoice_pdf(
        self,
        invoice: dict,
        settings: dict[str, str],
        output_path: str | Path,
    ) -> Path:
        pages = self.weight_renderer.render(invoice, settings)
        return self._export_pdf(pages, output_path)

    def export_customer_statement_pdf(
        self,
        statement: dict,
        settings: dict[str, str],
        output_path: str | Path,
    ) -> Path:
        pages = self.statement_renderer.render(statement, settings)
        return self._export_pdf(pages, output_path)

    def render_weight_invoice_images(
        self,
        invoice: dict,
        settings: dict[str, str],
    ) -> list[QImage]:
        return self.weight_renderer.render(invoice, settings)

    def render_customer_statement_images(
        self,
        statement: dict,
        settings: dict[str, str],
    ) -> list[QImage]:
        return self.statement_renderer.render(statement, settings)

    def _preview_pages(
        self,
        pages: list[QImage],
        *,
        title: str,
        settings: dict[str, str],
        parent: QWidget | None,
    ) -> None:
        printer = self._create_printer(str(settings.get("printer_name", "")))
        self._apply_a4_layout(printer)
        preview = QPrintPreviewDialog(printer, parent)
        preview.setWindowTitle(title)
        preview.resize(1100, 850)
        preview.paintRequested.connect(
            lambda requested_printer: self._paint_pages(requested_printer, pages)
        )
        preview.exec()

    def _export_pdf(self, pages: list[QImage], output_path: str | Path) -> Path:
        path = Path(output_path).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
        printer.setOutputFileName(str(path))
        self._apply_a4_layout(printer)
        self._paint_pages(printer, pages)
        if not path.exists() or path.stat().st_size <= 0:
            raise RuntimeError("تعذر إنشاء ملف PDF")
        return path

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
