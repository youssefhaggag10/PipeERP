from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.core.config import AppConfig
from app.services.first_run_service import FirstRunService


class FirstRunDialog(QDialog):
    def __init__(self, service: FirstRunService) -> None:
        super().__init__()
        self.service = service
        self.setWindowTitle(f"إعداد أول تشغيل - {AppConfig.COMPANY_NAME}")
        self.setMinimumWidth(460)
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("إنشاء مدير النظام")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignCenter)

        message = QLabel(
            "هذه الشاشة تظهر مرة واحدة فقط. أنشئ حساب المدير الذي سيستخدمه المصنع."
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignCenter)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("مثال: admin")
        self.username_input.setText("admin")

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("اسم المدير بالكامل")

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("8 أحرف على الأقل")

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText("أعد كتابة كلمة المرور")
        self.confirm_input.returnPressed.connect(self._create_admin)

        form = QFormLayout()
        form.addRow("اسم المستخدم", self.username_input)
        form.addRow("اسم المدير", self.full_name_input)
        form.addRow("كلمة المرور", self.password_input)
        form.addRow("تأكيد كلمة المرور", self.confirm_input)

        create_button = QPushButton("إنشاء حساب المدير")
        create_button.clicked.connect(self._create_admin)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)
        layout.addWidget(title)
        layout.addWidget(message)
        layout.addLayout(form)
        layout.addWidget(create_button)

    def _create_admin(self) -> None:
        password = self.password_input.text()
        if password != self.confirm_input.text():
            QMessageBox.warning(self, "تنبيه", "كلمتا المرور غير متطابقتين")
            self.password_input.clear()
            self.confirm_input.clear()
            self.password_input.setFocus()
            return

        try:
            self.service.create_initial_admin(
                username=self.username_input.text(),
                full_name=self.full_name_input.text(),
                password=password,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تعذر إنشاء المدير", str(error))
            return

        QMessageBox.information(
            self,
            "تم الإعداد",
            "تم إنشاء حساب المدير بنجاح. استخدم بياناته في شاشة تسجيل الدخول.",
        )
        self.accept()


__all__ = ["FirstRunDialog"]
