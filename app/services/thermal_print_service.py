from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt, QUrl
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QTextDocument
from PySide6.QtPrintSupport import QPrinter, QPrinterInfo, QPrintPreviewWidget
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.services.receipt_template_service import build_sales_receipt_html


class ThermalPrintService:
    PAPER_WIDTH_MM = 80.0
    PRINTABLE_WIDTH_MM = 72.0
    SIDE_MARGIN_MM = 4.0
    TOP_MARGIN_MM = 3.0
    BOTTOM_MARGIN_MM = 4.0
    HEIGHT_ALLOWANCE_MM = 6.0
    MIN_RECEIPT_HEIGHT_MM = 180.0

    def __init__(self) -> None:
        self._printing = False

    def preview_sales_invoice(
        self,
        invoice: dict,
        settings: dict[str, str],
        parent: QWidget | None = None,
    ) -> None:
        document = self._build_document(invoice, settings)
        receipt_height_mm = self._measure_receipt_height(document)

        preview_printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        self._apply_page_layout(preview_printer, receipt_height_mm)

        dialog = QDialog(parent)
        dialog.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        dialog.setWindowTitle(
            f"معاينة فاتورة {invoice['invoice_number']} — رول 80 مم"
        )
        dialog.resize(920, 800)

        preview = QPrintPreviewWidget(preview_printer, dialog)
        preview.setZoomMode(QPrintPreviewWidget.ZoomMode.FitToWidth)
        preview.paintRequested.connect(
            lambda requested_printer: self._paint_document(
                requested_printer,
                document,
                receipt_height_mm,
                show_errors=False,
                parent=dialog,
            )
        )

        printer_name = str(settings.get("printer_name", "")).strip()
        printer_label = QLabel(
            f"الطابعة المحددة: {printer_name or 'لم يتم اختيار طابعة'}"
        )
        printer_label.setObjectName("subtitleLabel")

        print_button = QPushButton("طباعة الفاتورة")
        print_button.setDefault(True)
        print_button.clicked.connect(
            lambda: self._print_to_configured_printer(
                document,
                receipt_height_mm,
                printer_name,
                print_button,
                dialog,
            )
        )

        close_button = QPushButton("إغلاق")
        close_button.setObjectName("secondaryButton")
        close_button.clicked.connect(dialog.reject)

        actions = QHBoxLayout()
        actions.addWidget(printer_label)
        actions.addStretch()
        actions.addWidget(close_button)
        actions.addWidget(print_button)

        layout = QVBoxLayout(dialog)
        layout.addWidget(preview)
        layout.addLayout(actions)

        preview.updatePreview()
        dialog.exec()

    def _print_to_configured_printer(
        self,
        document: QTextDocument,
        receipt_height_mm: float,
        printer_name: str,
        print_button: QPushButton,
        parent: QWidget,
    ) -> None:
        if self._printing:
            return

        printer_info = self._find_printer(printer_name)
        if printer_info is None:
            QMessageBox.warning(
                parent,
                "الطابعة غير موجودة",
                "الطابعة المحددة غير متاحة حاليًا. "
                "اختر اسم الطابعة الصحيح من الإعدادات ثم أعد المحاولة.",
            )
            return

        answer = QMessageBox.question(
            parent,
            "تأكيد الطباعة",
            f"سيتم إرسال Job واحد إلى الطابعة:\n{printer_info.printerName()}\n"
            "هل تريد المتابعة؟",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self._printing = True
        print_button.setEnabled(False)
        try:
            printer = QPrinter(printer_info, QPrinter.PrinterMode.HighResolution)
            succeeded = self._paint_document(
                printer,
                document,
                receipt_height_mm,
                show_errors=True,
                parent=parent,
            )
            if succeeded:
                QMessageBox.information(
                    parent,
                    "تم إرسال الفاتورة",
                    "تم إرسال Job طباعة واحد إلى الطابعة.",
                )
        finally:
            print_button.setEnabled(True)
            self._printing = False

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
        document.setTextWidth(printable_width_points)
        document.adjustSize()
        document.setTextWidth(printable_width_points)

        content_height_points = max(
            1.0,
            float(document.documentLayout().documentSize().height()),
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
        *,
        show_errors: bool,
        parent: QWidget,
    ) -> bool:
        self._apply_page_layout(printer, receipt_height_mm)

        printable_width_points = self.PRINTABLE_WIDTH_MM * 72.0 / 25.4
        document.setTextWidth(printable_width_points)
        content_height_points = max(
            1.0,
            float(document.documentLayout().documentSize().height()),
        )

        painter = QPainter()
        if not painter.begin(printer):
            if show_errors:
                QMessageBox.critical(
                    parent,
                    "تعذر بدء الطباعة",
                    "تعذر فتح الطابعة أو بدء Job الطباعة.",
                )
            return False

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
        return True

    def _apply_page_layout(
        self,
        printer: QPrinter,
        receipt_height_mm: float,
    ) -> None:
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

    @staticmethod
    def _find_printer(configured_name: str) -> QPrinterInfo | None:
        configured = configured_name.strip().casefold()
        if not configured:
            return None
        for printer_info in QPrinterInfo.availablePrinters():
            if printer_info.printerName().strip().casefold() == configured:
                return printer_info
        return None

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