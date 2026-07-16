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
from app.repositories.admin_only_crm_repository import AdminOnlyCRMRepository
from app.repositories.automated_inventory_repository import AutomatedInventoryRepository
from app.repositories.base_material_scrap_cost_repository import (
    BaseMaterialScrapCostRepository,
)
from app.repositories.detailed_return_refund_repository import DetailedReturnRefundRepository
from app.repositories.partner_repository import PartnerRepository
from app.repositories.print_settings_repository import PrintSettingsRepository
from app.repositories.return_refund_invoice_repository import ReturnRefundInvoiceRepository
from app.repositories.sales_repository import SalesRepository
from app.repositories.strict_product_repository import StrictProductRepository
from app.repositories.supplier_cost_purchase_repository import (
    SupplierCostPurchaseRepository,
)
from app.repositories.system_admin_repository import SystemAdminRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.services.crm_customer_sync import CRMCustomerSync
from app.ui.admin_only_crm_page import AdminOnlyCRMPage
from app.ui.backup_settings_page import BackupPrintSettingsPage
from app.ui.clickable_summary_accounts_page import ClickableSummaryAccountsPage
from app.ui.crm_page import CRMPage
from app.ui.dashboard import DashboardPage
from app.ui.inventory_page import InventoryPage
from app.ui.lot_balances_page import LotBalancesPage
from app.ui.partners_page import PartnersPage
from app.ui.replanned_manufacturing_page import ReplannedManufacturingPage
from app.ui.reports_page import ReportsPage
from app.ui.stock_card_page import StockCardPage
from app.ui.strict_products_page import StrictProductsPage
from app.ui.table_readability import configure_tables_in_widget
from app.ui.treasury_order_pages import (
    TreasuryPurchaseAccountingPage,
    TreasurySalesAccountingPageWithPrint,
)
from app.ui.warehouse_page import WarehousePage
from app.ui.watermark_overlay import WatermarkOverlay


class MainWindow(QMainWindow):
    def __init__(self, current_user: User, database: Database) -> None:
        super().__init__()
        self.setWindowTitle("3A PIPE - PipeERP")
        self.resize(1200, 760)
        self.setLayoutDirection(Qt.RightToLeft)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(240)
        self.navigation.currentRowChanged.connect(self.pages_changed)

        admin_repository = SystemAdminRepository(database, current_user)
        product_repository = StrictProductRepository(database)
        inventory_repository = AutomatedInventoryRepository(database)
        partner_repository = PartnerRepository(database)
        purchase_repository = SupplierCostPurchaseRepository(database)
        sales_repository = SalesRepository(database)
        warehouse_repository = WarehouseRepository(database)
        accounting_repository = DetailedReturnRefundRepository(database)
        invoice_repository = ReturnRefundInvoiceRepository(database)
        manufacturing_repository = BaseMaterialScrapCostRepository(database)
        self.print_settings_repository = PrintSettingsRepository(database)
        crm_repository = AdminOnlyCRMRepository(database, current_user)
        self.crm_sync = CRMCustomerSync(database, current_user)

        self.pages = QStackedWidget()
        self.watermark_overlay = WatermarkOverlay(self.pages)
        self._refresh_watermark()

        if admin_repository.has_permission("dashboard"):
            self.add_page("الرئيسية", DashboardPage(product_repository, inventory_repository))
        if admin_repository.has_permission("crm"):
            self.crm_sync.sync()
            self.add_page("CRM متابعة العملاء", AdminOnlyCRMPage(crm_repository))
        if admin_repository.has_permission("products"):
            self.add_page("الأصناف", StrictProductsPage(product_repository))
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
                TreasuryPurchaseAccountingPage(
                    purchase_repository,
                    partner_repository,
                    product_repository,
                    warehouse_repository,
                ),
            )
        if admin_repository.has_permission("sales"):
            self.add_page(
                "المبيعات",
                TreasurySalesAccountingPageWithPrint(
                    sales_repository,
                    partner_repository,
                    product_repository,
                    warehouse_repository,
                ),
            )
        if admin_repository.has_permission("accounts"):
            self.add_page(
                "الحسابات",
                ClickableSummaryAccountsPage(
                    accounting_repository,
                    partner_repository,
                    invoice_repository,
                ),
            )
        if admin_repository.has_permission("stock_card"):
            self.add_page("كارت الصنف", StockCardPage(inventory_repository))
        if admin_repository.has_permission("manufacturing"):
            self.add_page(
                "التصنيع",
                ReplannedManufacturingPage(
                    manufacturing_repository,
                    product_repository,
                    warehouse_repository,
                ),
            )
        if admin_repository.has_permission("reports"):
            self.add_page("التقارير", ReportsPage(accounting_repository, partner_repository))
        if admin_repository.has_permission("settings"):
            settings_page = BackupPrintSettingsPage(
                self.print_settings_repository,
                admin_repository,
                database.path,
            )
            settings_page.watermark_settings_changed.connect(self._refresh_watermark)
            self.add_page("الإعدادات", settings_page)

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

    def _refresh_watermark(self) -> None:
        self.watermark_overlay.apply_settings(
            self.print_settings_repository.get_settings()
        )

    def add_page(self, title: str, page: QWidget) -> None:
        configure_tables_in_widget(page)
        self.navigation.addItem(title)
        self.pages.addWidget(page)
        self.watermark_overlay.raise_()

    def pages_changed(self, index: int) -> None:
        if index < 0:
            return
        page = self.pages.widget(index)
        if isinstance(page, CRMPage):
            self.crm_sync.sync()
        if hasattr(page, "reload"):
            page.reload()
        configure_tables_in_widget(page)
        self.pages.setCurrentIndex(index)
        self.watermark_overlay.raise_()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showMaximized()
            else:
                self.showFullScreen()
            return
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showMaximized()
            return
        super().keyPressEvent(event)


__all__ = ["MainWindow"]
