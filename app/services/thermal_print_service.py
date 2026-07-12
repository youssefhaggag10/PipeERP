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
