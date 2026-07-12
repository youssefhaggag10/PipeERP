from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from app.repositories.invoice_repository import InvoiceRepository
from app.services.invoice_service import INVOICE_STATUS_LABELS
from app.ui.order_details_dialog import OrderDetailsDialog
from app.ui.purchase_page import PurchasePage
from app.ui.sales_page import SalesPage
from app.utils.datetime_utils import format_egypt_datetime

INVOICE_COL