from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
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
from app.ui.order_details_dialog import OrderDetailsDialog
from app.ui.purchase_page import PurchasePage
from app.ui.sales_page import SalesPage


class _PaymentOrderMixin:
    paid_input