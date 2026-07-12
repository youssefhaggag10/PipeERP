from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.database.connection import Database
from app.models.user import User
from app.repositories.accounting_repository import AccountingRepository
from app.repositories.admin_repository import AdminRepository
from app.repositories.crm_repository import CRMRepository
from app.repositories.inventory_repository import InventoryRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.repositories.partner_repository import PartnerRepository
from app.repositories.print_settings_repository import PrintSettingsRepository
from app.repositories.product_repository import ProductRepository
from app.repositories.purchase_repository import PurchaseRepository
from app.repositories.sales_repository import SalesRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.services.crm_customer_sync import CRMCustomerSync
from app.ui.accounting_order_pages import PurchaseAccountingPage, SalesAccountingPage
from app.ui.accounts_page import AccountsPage
from app.ui.crm_page import CRMPage
from app.ui.dashboard import DashboardPage
from app.ui.inventory_page import InventoryPage
from app.ui.lot_balances_page import LotBalancesPage
from app.ui.partners_page import PartnersPage
from app.ui.products_page import ProductsPage
from app.ui.reports_page import ReportsPage
from app.ui.settings_page import SettingsPage
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

        admin_repository = AdminRepository(database, current_user)
        product_repository = ProductRepository(database)
        inventory_repository = InventoryRepository(database)
        partner_repository = PartnerRepository(database)
        purchase_repository = PurchaseRepository(database)
        sales_repository = SalesRepository(database)
        warehouse_repository = WarehouseRepository(database)
        accounting_repository = AccountingRepository(database)
        invoice_repository = InvoiceRepository(database)
        print_settings_repository = PrintSettingsRepository(database)
        crm_repository = CRMRepository(database, current_user)
        self.crm_sync = CRMCustomerSync(database, current_user)

        self.pages = QStackedWidget()

        if admin_repository.has_permission("dashboard"):
            self.add_page("الرئيسية", DashboardPage(product_repository, inventory_repository))
        if admin_repository.has_permission("crm"):
            self.crm_sync.sync()
            self.add_page("CRM متابعة العملاء", CRMPage(crm_repository))
        if admin_repository.has_permission("products"):
            self.add_page("الأصناف", ProductsPage(product_repository))
        if admin_repository.has_permission("suppliers"):
            self.add_page("الموردين", PartnersPage("الموردين", "supplier", partner_repository))
        if admin_repository.has_permission("customers"):
            self.add_page("العملاء", PartnersPage("العملاء", "customer", partner_repository))
        if admin_repository.has_permission("warehouse"):
            self.add_page("إعداد المخزن", WarehousePage(warehouse_repository))
        if admin_repository.has_permission("inventory"):
            self.add_page("رصيد المخزون", InventoryPage(inventory_repository))
        if admin_repository.has_permission("lots"):
            self.add_page("أرصدة الدفعات", LotBalancesPage(inventory_repository))
        if admin_repository.has_permission("purchases"):
            self.add_page(
                "المشتريات",
                PurchaseAccountingPage(
                    purchase_repository,
                    partner_repository,
                    product_repository,
                    warehouse_repository,
                ),
            )
        if admin_repository.has_permission("sales"):
            self.add_page(
                "المبيعات",
                SalesAccountingPage(
                    sales_repository,
                    partner_repository,
                    product_repository,
                    warehouse_repository,
                ),
            )
        if admin_repository.has_permission("accounts"):
            self.add_page(
                "الحسابات",
                AccountsPage(accounting_repository, partner_repository, invoice_repository),
            )
        if admin_repository.has_permission("stock_card"):
            self.add_page("كارت الصنف", StockCardPage(inventory_repository))
        if admin_repository.has_permission("manufacturing"):
            self.add_page(
                "التصنيع",
                TransactionsListPage(
                    "التصنيع", "أوامر التصنيع", ["رقم الأمر", "المنتج", "الكمية", "الحالة"]
                ),
            )
        if admin_repository.has_permission("reports"):
            self.add_page("التقارير", ReportsPage(accounting_repository, partner_repository))
        if admin_repository.has_permission("settings"):
            self.add_page(
                "الإعدادات",
                SettingsPage(print_settings_repository, admin_repository),
            )

        if self.pages.count() == 0:
            empty_page = QWidget()
            empty_layout = QVBoxLayout(empty_page)
            empty_message = QLabel("لا توجد صلاحيات مخصصة لهذا المستخدم. تواصل مع الأدمن.")
            empty_message.setAlignment(Qt.AlignCenter)
            empty_message.setObjectName("titleLabel")
            empty_layout.addWidget(empty_message)
            self.add_page("لا توجد صلاحيات", empty_page)

        header = QLabel(f"3A PIPE — {current_user.display_name}")
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
        if index < 0:
            return
        page = self.pages.widget(index)
        if isinstance(page, CRMPage):
            self.crm_sync.sync()
        if hasattr(page, "reload"):
            page.reload()
        self.pages.setCurrentIndex(index)
