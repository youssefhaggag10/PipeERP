from PySide6.QtCore import QPoint, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.database.connection import Database
from app.models.user import User
from app.repositories.admin_only_crm_repository import AdminOnlyCRMRepository
from app.repositories.automated_inventory_repository import AutomatedInventoryRepository
from app.repositories.detailed_return_refund_repository import (
    DetailedReturnRefundRepository,
)
from app.repositories.order_completion_manufacturing_repository import (
    OrderCompletionManufacturingRepository,
)
from app.repositories.partner_repository import PartnerRepository
from app.repositories.print_settings_repository import PrintSettingsRepository
from app.repositories.return_refund_invoice_repository import (
    ReturnRefundInvoiceRepository,
)
from app.repositories.sales_repository import SalesRepository
from app.repositories.standalone_weight_sales_repository import (
    StandaloneWeightSalesRepository,
)
from app.repositories.strict_product_repository import StrictProductRepository
from app.repositories.supplier_cost_purchase_repository import (
    SupplierCostPurchaseRepository,
)
from app.repositories.system_admin_repository import SystemAdminRepository
from app.repositories.warehouse_repository import WarehouseRepository
from app.services.crm_customer_sync import CRMCustomerSync
from app.ui.admin_only_crm_page import AdminOnlyCRMPage
from app.ui.appearance import AppearanceSettingsRepository, apply_appearance
from app.ui.backup_settings_page import BackupPrintSettingsPage
from app.ui.crm_activity_center import CRMActivityCenter
from app.ui.crm_page import CRMPage
from app.ui.dashboard import DashboardPage
from app.ui.inventory_page import InventoryPage
from app.ui.lot_balances_page import LotBalancesPage
from app.ui.partners_page import PartnersPage
from app.ui.production_run_page import ProductionRunManufacturingPage
from app.ui.reports_page import ReportsPage
from app.ui.responsive_accounts_page import ResponsiveAccountsPage
from app.ui.sales_navigation_delegate import (
    SALES_DROPDOWN_ROLE,
    NavigationListWidget,
    SalesNavigationDelegate,
)
from app.ui.stock_card_page import StockCardPage
from app.ui.strict_products_page import StrictProductsPage
from app.ui.table_readability import configure_tables_in_widget
from app.ui.treasury_order_pages import (
    TreasuryPurchaseAccountingPage,
    TreasurySalesAccountingPageWithPrint,
)
from app.ui.warehouse_page import WarehousePage
from app.ui.watermark_overlay import WatermarkOverlay
from app.ui.weight_card_sales_page import WeightCardSalesPage

PAGE_INDEX_ROLE = Qt.UserRole


class MainWindow(QMainWindow):
    def __init__(self, current_user: User, database: Database) -> None:
        super().__init__()
        self.setWindowTitle("3A PIPE - PipeERP")
        self.resize(1200, 760)
        self.setLayoutDirection(Qt.RightToLeft)
        self.database = database
        self.appearance_repository = AppearanceSettingsRepository(database)
        self.page_indexes: dict[str, int] = {}
        self.crm_page: AdminOnlyCRMPage | None = None
        self.activity_center: CRMActivityCenter | None = None
        self.sales_navigation_item: QListWidgetItem | None = None
        self.weight_sales_page_index: int | None = None

        self.navigation = NavigationListWidget()
        self.navigation.setFixedWidth(240)
        self.navigation.setItemDelegate(SalesNavigationDelegate(self.navigation))
        self.navigation.currentItemChanged.connect(self._navigation_item_changed)
        self.navigation.sales_dropdown_requested.connect(self._show_sales_weight_menu)
        self.sales_weight_menu = QMenu(self.navigation)
        self.weight_sales_action = self.sales_weight_menu.addAction("البيع بالوزن / الكارتة")
        self.weight_sales_action.triggered.connect(self._open_weight_sales_page)

        admin_repository = SystemAdminRepository(database, current_user)
        product_repository = StrictProductRepository(database)
        inventory_repository = AutomatedInventoryRepository(database)
        partner_repository = PartnerRepository(database)
        purchase_repository = SupplierCostPurchaseRepository(database)
        sales_repository = SalesRepository(database)
        weight_sales_repository = StandaloneWeightSalesRepository(database)
        warehouse_repository = WarehouseRepository(database)
        accounting_repository = DetailedReturnRefundRepository(database)
        invoice_repository = ReturnRefundInvoiceRepository(database)
        manufacturing_repository = OrderCompletionManufacturingRepository(database)
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
            self.crm_page = AdminOnlyCRMPage(crm_repository)
            self.add_page("CRM متابعة العملاء", self.crm_page)
            self.activity_center = CRMActivityCenter(crm_repository, self)
            self.activity_center.open_crm_requested.connect(self._open_crm_activities)
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
            normal_sales_index = self.add_page(
                "المبيعات",
                TreasurySalesAccountingPageWithPrint(
                    sales_repository,
                    partner_repository,
                    product_repository,
                    warehouse_repository,
                ),
                add_navigation=False,
            )
            self.weight_sales_page_index = self.add_page(
                "بيع بالوزن / الكارتة",
                WeightCardSalesPage(
                    weight_sales_repository,
                    partner_repository,
                    product_repository,
                    warehouse_repository,
                ),
                add_navigation=False,
            )
            self._add_sales_navigation(normal_sales_index)
        if admin_repository.has_permission("accounts"):
            self.add_page(
                "الحسابات",
                ResponsiveAccountsPage(
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
                ProductionRunManufacturingPage(
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
            settings_page.appearance_settings_changed.connect(self._apply_appearance)
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
        header.setObjectName("appHeader")
        header_layout = QHBoxLayout()
        header_layout.addWidget(header)
        header_layout.addStretch()
        if self.activity_center is not None:
            header_layout.addWidget(self.activity_center)

        content_layout = QVBoxLayout()
        content_layout.addLayout(header_layout)
        content_layout.addWidget(self.pages)

        layout = QHBoxLayout()
        layout.addLayout(content_layout)
        layout.addWidget(self.navigation)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.navigation.setCurrentRow(0)

    def _refresh_watermark(self) -> None:
        self.watermark_overlay.apply_settings(self.print_settings_repository.get_settings())

    def _apply_appearance(self) -> None:
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_appearance(app, self.appearance_repository)
        for index in range(self.pages.count()):
            configure_tables_in_widget(self.pages.widget(index))
        if self.activity_center is not None:
            self.activity_center.refresh()

    def add_page(self, title: str, page: QWidget, *, add_navigation: bool = True) -> int:
        configure_tables_in_widget(page)
        index = self.pages.count()
        self.page_indexes[title] = index
        self.pages.addWidget(page)
        if add_navigation:
            item = QListWidgetItem(title)
            item.setData(PAGE_INDEX_ROLE, index)
            self.navigation.addItem(item)
        self.watermark_overlay.raise_()
        return index

    def _add_sales_navigation(self, normal_index: int) -> None:
        item = QListWidgetItem("المبيعات")
        item.setData(PAGE_INDEX_ROLE, normal_index)
        item.setData(SALES_DROPDOWN_ROLE, True)
        self.navigation.addItem(item)
        self.sales_navigation_item = item

    def _show_sales_weight_menu(
        self,
        _item: QListWidgetItem,
        global_position: QPoint,
    ) -> None:
        self.sales_weight_menu.popup(global_position)

    def _open_weight_sales_page(self) -> None:
        if self.sales_navigation_item is None or self.weight_sales_page_index is None:
            return
        with QSignalBlocker(self.navigation):
            self.navigation.setCurrentItem(self.sales_navigation_item)
        self.pages_changed(self.weight_sales_page_index)

    def _navigation_item_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if current is None:
            return
        page_index = current.data(PAGE_INDEX_ROLE)
        if page_index is None:
            return
        self.pages_changed(int(page_index))

    def _open_crm_activities(self) -> None:
        index = self.page_indexes.get("CRM متابعة العملاء")
        if index is None:
            return
        self._select_navigation_for_page(index)
        self.pages_changed(index)
        if self.crm_page is not None and hasattr(self.crm_page, "tabs"):
            for tab_index in range(self.crm_page.tabs.count()):
                if self.crm_page.tabs.tabText(tab_index).strip() == "الأنشطة":
                    self.crm_page.tabs.setCurrentIndex(tab_index)
                    break
            self.crm_page.reload()

    def _select_navigation_for_page(self, page_index: int) -> None:
        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            if item.data(PAGE_INDEX_ROLE) == page_index:
                self.navigation.setCurrentItem(item)
                return

    def pages_changed(self, index: int) -> None:
        if index < 0 or index >= self.pages.count():
            return
        page = self.pages.widget(index)
        if isinstance(page, CRMPage):
            self.crm_sync.sync()
        if hasattr(page, "reload"):
            page.reload()
        configure_tables_in_widget(page)
        self.pages.setCurrentIndex(index)
        self.watermark_overlay.raise_()
        if self.activity_center is not None:
            self.activity_center.refresh()

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


__all__ = [
    "MainWindow",
    "NavigationListWidget",
    "SalesNavigationDelegate",
]
