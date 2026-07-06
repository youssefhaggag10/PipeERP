from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QMainWindow, QStackedWidget, QWidget

from app.models.user import User
from app.ui.dashboard import DashboardPage
from app.ui.placeholder_page import PlaceholderPage


class MainWindow(QMainWindow):
    def __init__(self, current_user: User) -> None:
        super().__init__()
        self.current_user = current_user
        self.setWindowTitle("PipeERP")
        self.resize(1200, 760)
        self.setLayoutDirection(Qt.RightToLeft)

        self.navigation = QListWidget()
        self.navigation.setFixedWidth(240)
        self.navigation.currentRowChanged.connect(self.pages_changed)

        self.pages = QStackedWidget()
        self.add_page("الرئيسية", DashboardPage())
        self.add_page("الأصناف", PlaceholderPage("الأصناف", "قريبًا"))
        self.add_page("المخازن", PlaceholderPage("المخازن", "قريبًا"))
        self.add_page("المشتريات", PlaceholderPage("المشتريات", "قريبًا"))
        self.add_page("التصنيع", PlaceholderPage("التصنيع", "قريبًا"))
        self.add_page("المبيعات", PlaceholderPage("المبيعات", "قريبًا"))

        layout = QHBoxLayout()
        layout.addWidget(self.pages)
        layout.addWidget(self.navigation)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)
        self.navigation.setCurrentRow(0)

    def add_page(self, title: str, page: QWidget) -> None:
        self.navigation.addItem(title)
        self.pages.addWidget(page)

    def pages_changed(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
