from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout

from app.models.user import User
from app.services.auth_service import AuthService


class LoginDialog(QDialog):
    def __init__(self, auth_service: AuthService) -> None:
        super().__init__()
        self.auth_service = auth_service
        self.current_user: User | None = None

        self.setWindowTitle("تسجيل الدخول - PipeERP")
        self.setMinimumWidth(420)
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("بايب ERP")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)

        subtitle = QLabel("نظام إدارة تصنيع المواسير البلاستيك")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignCenter)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("اسم المستخدم")
        self.username_input.setText("admin")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("كلمة المرور")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setText("admin123")
        self.password_input.returnPressed.connect(self._login)

        login_button = QPushButton("دخول")
        login_button.clicked.connect(self._login)

        cancel_button = QPushButton("إلغاء")
        cancel_button.setObjectName("secondaryButton")
        cancel_button.clicked.connect(self.reject)

        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(login_button)
        buttons_layout.addWidget(cancel_button)

        layout = QVBoxLayout()
        layout.setSpacing(14)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(QLabel("اسم المستخدم"))
        layout.addWidget(self.username_input)
        layout.addWidget(QLabel("كلمة المرور"))
        layout.addWidget(self.password_input)
        layout.addLayout(buttons_layout)
        self.setLayout(layout)

    def _login(self) -> None:
        user = self.auth_service.authenticate(
            self.username_input.text(),
            self.password_input.text(),
        )
        if user is None:
            QMessageBox.warning(self, "خطأ", "اسم المستخدم أو كلمة المرور غير صحيحة")
            return
        self.current_user = user
        self.accept()
