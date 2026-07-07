from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.database.connection import Database
from app.models.user import User
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.partner_repository import PartnerRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.repositories.sales_repository import SalesRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.ui.dashboard import DashboardPage
from app.ui.inventory_page import InventoryPage
from app.ui.partners_page import PartnersPage
from app.ui.placeholder_page import PlaceholderPage
from app.ui.products_page import ProductsPage
from app.ui.purchase_page import PurchasePage
from app.ui.sales_page import SalesPage
from app.ui.stock_card_page import StockCardPage
from app.ui.transactions_list_page import TransactionsListPage
from app.ui.warehouse_page import WarehousePage


class MainWindow(QMainWindow):
    def __init__(self, current_user: User, database: Database) -> None:
        super().__init__()
        self.setWindowTitle("3A PIPE - PipeERP")
        self.resize(1200, 760)
        self.setLayoutDirection(Qt.RightToLeft)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(240)
        self.navigation.currentRowChanged.connect(self.pages_changed)

        product_repository = ProductRepository(database)
        inventory_repository = InventoryRepository(database)
        partner_repository = PartnerRepository(database)
        purchase_repository = PurchaseRepository(database)
        sales_repository = SalesRepository(database)
        warehouse_repository = WarehouseRepository(database)

        self.pages = QStackedWidget()
        self.add_page("الرئيسية", DashboardPage(product_repository, inventory_repository))
        self.add_page("الأصناف", ProductsPage(product_repository))
        self.add_page("الموردين", PartnersPage("الموردين", "supplier", partner_repository))
        self.add_page("العملاء", PartnersPage("العملاء", "customer", partner_repository))
        self.add_page("إعداد المخزن", WarehousePage(warehouse_repository))
        self.add_page("رصيد المخزون", InventoryPage(inventory_repository))
        self.add_page("المشتريات", PurchasePage(purchase_repository, partner_repository, product_repository))
        self.add_page("المبيعات", SalesPage(sales_repository, partner_repository, product_repository))
        self.add_page("كارت الصنف", StockCardPage(inventory_repository))
        self.add_page("التصنيع", TransactionsListPage("التصنيع", "أوامر التصنيع", ["رقم الأمر", "المنتج", "الكمية", "الحالة"]))
        self.add_page("التقارير", PlaceholderPage("التقارير", "تقارير الإنتاج والمخزون والتكلفة"))
        self.add_page("الإعدادات", PlaceholderPage("الإعدادات", "المستخدمين والإعدادات العامة"))

        header = QLabel("3A PIPE")
        content_layout = QVBoxLayout()
        content_layout.addWidget(header)
        content_layout.addWidget(self.pages)

        layout = QHBoxLayout()
        layout.addLayout(content_layout)
        layout.addWidget(self.navigation)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.navigation.setCurrentRow(0)

    def add_page(self, title: str, page: QWidget) -> None:
        self.navigation.addItem(title)
        self.pages.addWidget(page)

    def pages_changed(self, index: int) -> None:
        if index >= 0:
            page = self.pages.widget(index)
            if hasattr(page, "reload"):
                page.reload()
            self.pages.setCurrentIndex(index)
