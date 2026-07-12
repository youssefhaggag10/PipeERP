from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.repositories.admin_repository import AdminRepository


class SettingsPage(QWidget):
    def __init__(self, admin_repository: AdminRepository) -> None:
        super().__init__()
        self.admin_repository = admin_repository
        self.selected_user_id: int | None = None
        self.permission_checks: dict[str, QCheckBox] = {}
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الإعدادات")
        title.setObjectName("titleLabel")
        subtitle = QLabel("إدارة المستخدمين والصلاحيات وإعادة ضبط النظام")
        subtitle.setObjectName("subtitleLabel")

        self.tabs = QTabWidget()
        if self.admin_repository.has_permission("user_management"):
            self.tabs.addTab(self._build_users_tab(), "المستخدمون والصلاحيات")
        if self.admin_repository.has_permission("system_reset"):
            self.tabs.addTab(self._build_reset_tab(), "إعادة ضبط النظام")
        if self.tabs.count() == 0:
            empty_tab = QWidget()
            empty_layout = QVBoxLayout(empty_tab)
            empty_message = QLabel("لا توجد إعدادات متاحة لهذا المستخدم")
            empty_message.setAlignment(Qt.AlignCenter)
            empty_layout.addWidget(empty_message)
            self.tabs.addTab(empty_tab, "الإعدادات")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs)
        self.reload()

    def _build_users_tab(self) -> QWidget:
        tab = QWidget()
        self.users_table = QTableWidget(0, 5)
        self.users_table.setHorizontalHeaderLabels(
            ["الكود", "اسم المستخدم", "الاسم الكامل", "الدور", "الحالة"]
        )
        self.users_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.users_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.users_table.itemSelectionChanged.connect(self._load_selected_user)

        self.user_username = QLineEdit()
        self.user_full_name = QLineEdit()
        self.user_password = QLineEdit()
        self.user_password.setEchoMode(QLineEdit.Password)
        self.user_password.setPlaceholderText("اتركها فار