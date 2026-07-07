from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidget, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from app.database.connection import Database
from app.models.user import User
from app.repositories.product_repository import ProductRepository
from app.ui.dashboard import DashboardPage
from app.ui.placeholder_page import PlaceholderPage
from app.ui.products_page import ProductsPage


class MainWindow(QMainWindow):
    def __init__(self, current_user: User, database: Database) -> None:
        super().__init__()
        self.current_user = current_user
        self.database = database
        self.setWindowTitle("PipeERP")
        self.resize(1200, 760)
        self.setLayoutDirection(Qt.RightToLeft)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(240)
        self.navigation.currentRowChanged.connect(self.pages_changed)

        product_repository = ProductRepository(database)
        self.pages = QStackedWidget()
        self.add_page("الرئيسية", DashboardPage())
        self.add_page("الأصناف", ProductsPage(product_repository))
        self.add_page("المخازن", PlaceholderPage("المخازن", "حركات وأرصدة المخزون"))
        self.add_page("المشتريات", PlaceholderPage("المشتريات", "الموردين واللوتات وتكلفة الشراء"))
        self.add_page("التصنيع", PlaceholderPage("التصنيع", "أوامر التصنيع بالوزن والهالك"))
        self.add_page("المبيعات", PlaceholderPage("المبيعات", "فواتير العملاء والتسليم"))
        self.add_page("التقارير", PlaceholderPage("التقارير", "تقارير الإنتاج والمخزون والتكلفة"))
        self.add_page("الإعدادات", PlaceholderPage("الإعدادات", "المستخدمين والإعدادات العامة"))

        header = QLabel(f"مرحبًا، {current_user.display_name}")
        header.setObjectName("subtitleLabel")
        header.setAlignment(Qt.AlignLeft)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(header)
        content_layout.addWidget(self.pages)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
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
            self.pages.setCurrentIndex(index)
