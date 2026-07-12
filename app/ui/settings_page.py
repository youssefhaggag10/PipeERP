from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPrintSupport import QPrinterInfo
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.repositories.admin_repository import AdminRepository
from app.repositories.print_settings_repository import PrintSettingsRepository


class SettingsPage(QWidget):
    def __init__(
        self,
        repository: PrintSettingsRepository,
        admin_repository: AdminRepository,
    ) -> None:
        super().__init__()
        self.repository = repository
        self.admin_repository = admin_repository
        self.logo_source: str | None = None
        self.qr_source: str | None = None
        self.selected_user_id: int | None = None
        self.permission_checks: dict[str, QCheckBox] = {}
        self.setLayoutDirection(Qt.RightToLeft)

        title = QLabel("الإعدادات")
        title.setObjectName("titleLabel")
        subtitle = QLabel("إعدادات الطباعة والمستخدمين والصلاحيات وإعادة ضبط النظام")
        subtitle.setObjectName("subtitleLabel")

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_print_tab(), "الطباعة")
        if self.admin_repository.has_permission("user_management"):
            self.tabs.addTab(self._build_users_tab(), "المستخدمون والصلاحيات")
        if self.admin_repository.has_permission("system_reset"):
            self.tabs.addTab(self._build_reset_tab(), "إعادة ضبط النظام")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.tabs)
        self.reload()

    def _build_print_tab(self) -> QWidget:
        tab = QWidget()
        self.company_name_input = QLineEdit()
        self.address_input = QLineEdit()
        self.phones_input = QPlainTextEdit()
        self.phones_input.setPlaceholderText("رقم هاتف في كل سطر")
        self.phones_input.setFixedHeight(72)
        self.footer_input = QPlainTextEdit()
        self.footer_input.setFixedHeight(64)
        self.beneficiary_input = QLineEdit()
        self.instapay_input = QLineEdit()
        self.instapay_input.setLayoutDirection(Qt.LeftToRight)

        invoice_group = QGroupBox("رأس وتذييل فاتورة المبيعات")
        invoice_form = QFormLayout(invoice_group)
        invoice_form.addRow("اسم المصنع", self.company_name_input)
        invoice_form.addRow("العنوان", self.address_input)
        invoice_form.addRow("أرقام الهاتف", self.phones_input)
        invoice_form.addRow("نص أسفل الفاتورة", self.footer_input)

        self.printer_input = QComboBox()
        self.printer_input.setEditable(True)
        paper_width = QLineEdit("80 mm — مساحة الطباعة 72 mm")
        paper_width.setReadOnly(True)
        printer_group = QGroupBox("الطابعة الحرارية")
        printer_form = QFormLayout(printer_group)
        printer_form.addRow("الطابعة", self.printer_input)
        printer_form.addRow("مقاس الرول", paper_width)
        printer_note = QLabel(
            "الطباعة تتم عبر تعريف النظام للطابعة USB. ثبّت تعريف Star TSP100 على الجهاز."
        )
        printer_note.setObjectName("subtitleLabel")
        printer_note.setWordWrap(True)
        printer_form.addRow(printer_note)

        self.logo_preview = self._image_preview()
        self.qr_preview = self._image_preview()
        logo_button = QPushButton("اختيار لوجو جديد")
        logo_button.setObjectName("secondaryButton")
        logo_button.clicked.connect(self.choose_logo)
        qr_button = QPushButton("اختيار QR جديد")
        qr_button.setObjectName("secondaryButton")
        qr_button.clicked.connect(self.choose_qr)

        logo_widget = QWidget()
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.addWidget(self.logo_preview)
        logo_layout.addWidget(logo_button)
        logo_layout.addStretch()

        qr_widget = QWidget()
        qr_layout = QHBoxLayout(qr_widget)
        qr_layout.setContentsMargins(0, 0, 0, 0)
        qr_layout.addWidget(self.qr_preview)
        qr_layout.addWidget(qr_button)
        qr_layout.addStretch()

        payment_group = QGroupBox("الدفع عبر InstaPay")
        payment_form = QFormLayout(payment_group)
        payment_form.addRow("اسم المستفيد", self.beneficiary_input)
        payment_form.addRow("عنوان InstaPay", self.instapay_input)
        payment_form.addRow("اللوجو", logo_widget)
        payment_form.addRow("QR Code", qr_widget)

        save_button = QPushButton("حفظ إعدادات الطباعة")
        save_button.clicked.connect(self.save)
        reload_button = QPushButton("إلغاء التعديلات وإعادة التحميل")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self.reload)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(reload_button)
        actions.addStretch()

        columns = QHBoxLayout()
        columns.addWidget(invoice_group, 2)
        columns.addWidget(printer_group, 1)

        layout = QVBoxLayout(tab)
        layout.addLayout(columns)
        layout.addWidget(payment_group)
        layout.addLayout(actions)
        layout.addStretch()
        return tab

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
        self.user_password.setPlaceholderText("اتركها فارغة عند التعديل للاحتفاظ بالحالية")
        self.user_role = QComboBox()
        self.user_role.addItem("موظف", "employee")
        self.user_role.addItem("مشرف", "supervisor")
        self.user_role.addItem("مدير", "manager")
        self.user_role.addItem("أدمن", "admin")
        self.user_active = QCheckBox("مستخدم نشط")
        self.user_active.setChecked(True)

        form_group = QGroupBox("بيانات المستخدم")
        form = QFormLayout(form_group)
        form.addRow("اسم المستخدم", self.user_username)
        form.addRow("الاسم الكامل", self.user_full_name)
        form.addRow("كلمة المرور", self.user_password)
        form.addRow("الدور", self.user_role)
        form.addRow("", self.user_active)

        permissions_group = QGroupBox("الصلاحيات")
        permissions_grid = QGridLayout(permissions_group)
        for index, permission in enumerate(self.admin_repository.permission_catalog()):
            checkbox = QCheckBox(permission["name"])
            self.permission_checks[permission["code"]] = checkbox
            permissions_grid.addWidget(checkbox, index // 3, index % 3)

        new_button = QPushButton("مستخدم جديد")
        new_button.setObjectName("secondaryButton")
        new_button.clicked.connect(self._clear_user_form)
        save_button = QPushButton("حفظ المستخدم والصلاحيات")
        save_button.clicked.connect(self._save_user)
        delete_button = QPushButton("حذف المستخدم")
        delete_button.setObjectName("dangerButton")
        delete_button.clicked.connect(self._delete_user)
        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(new_button)
        actions.addWidget(delete_button)
        actions.addStretch()

        right = QVBoxLayout()
        right.addWidget(form_group)
        right.addWidget(permissions_group)
        right.addLayout(actions)
        right.addStretch()

        body = QHBoxLayout(tab)
        body.addWidget(self.users_table, 2)
        body.addLayout(right, 3)
        return tab

    def _build_reset_tab(self) -> QWidget:
        tab = QWidget()
        warning = QLabel(
            "إعادة ضبط النظام تمسح كل بيانات التشغيل: العملاء، الموردين، الأصناف، CRM، "
            "المخزون، أوامر البيع والشراء، الفواتير والمدفوعات. سيتم الاحتفاظ بالمستخدمين "
            "وإعدادات الطباعة فقط. لا يمكن التراجع إلا من نسخة احتياطية خارجية."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet("font-weight: bold; color: #dc2626;")
        reset_button = QPushButton("حذف كل البيانات وإرجاع النظام للصفر")
        reset_button.setObjectName("dangerButton")
        reset_button.clicked.connect(self._confirm_reset)
        layout = QVBoxLayout(tab)
        layout.addWidget(warning)
        layout.addSpacing(20)
        layout.addWidget(reset_button)
        layout.addStretch()
        return tab

    @staticmethod
    def _image_preview() -> QLabel:
        preview = QLabel("لا توجد صورة")
        preview.setAlignment(Qt.AlignCenter)
        preview.setFixedSize(220, 145)
        preview.setStyleSheet(
            "border: 1px solid #334155; background: white; color: #111827;"
        )
        return preview

    def reload(self) -> None:
        values = self.repository.get_settings()
        self.company_name_input.setText(values["company_name"])
        self.address_input.setText(values["address"])
        self.phones_input.setPlainText(values["phones"])
        self.footer_input.setPlainText(values["footer"])
        self.beneficiary_input.setText(values["beneficiary_name"])
        self.instapay_input.setText(values["instapay_handle"])
        self._reload_printers(values["printer_name"])
        self._set_preview(self.logo_preview, values["logo_path"])
        self._set_preview(self.qr_preview, values["qr_path"])
        self.logo_source = None
        self.qr_source = None
        if hasattr(self, "users_table"):
            self._reload_users()

    def _reload_users(self) -> None:
        users = self.admin_repository.list_users()
        self.users_table.setRowCount(len(users))
        for row_index, user in enumerate(users):
            values = [
                user["id"],
                user["username"],
                user["full_name"],
                user["role"],
                "نشط" if user["is_active"] else "موقوف",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setData(Qt.UserRole, user)
                self.users_table.setItem(row_index, column, item)
        self.users_table.resizeColumnsToContents()

    def _load_selected_user(self) -> None:
        row = self.users_table.currentRow()
        if row < 0:
            return
        item = self.users_table.item(row, 0)
        if item is None:
            return
        user = item.data(Qt.UserRole)
        self.selected_user_id = int(user["id"])
        self.user_username.setText(str(user["username"]))
        self.user_full_name.setText(str(user["full_name"]))
        self.user_password.clear()
        role_index = self.user_role.findData(str(user["role"]))
        self.user_role.setCurrentIndex(max(0, role_index))
        self.user_active.setChecked(bool(user["is_active"]))
        permissions = set(user["permissions"])
        for code, checkbox in self.permission_checks.items():
            checkbox.setChecked(code in permissions)
        self._update_permission_state()

    def _clear_user_form(self) -> None:
        self.selected_user_id = None
        self.users_table.clearSelection()
        self.user_username.clear()
        self.user_full_name.clear()
        self.user_password.clear()
        self.user_role.setCurrentIndex(0)
        self.user_active.setChecked(True)
        for checkbox in self.permission_checks.values():
            checkbox.setChecked(False)
            checkbox.setEnabled(True)

    def _update_permission_state(self) -> None:
        is_admin = self.user_role.currentData() == "admin"
        for checkbox in self.permission_checks.values():
            checkbox.setEnabled(not is_admin)
            if is_admin:
                checkbox.setChecked(True)

    def _save_user(self) -> None:
        permissions = {
            code for code, checkbox in self.permission_checks.items() if checkbox.isChecked()
        }
        try:
            self.admin_repository.save_user(
                user_id=self.selected_user_id,
                username=self.user_username.text(),
                full_name=self.user_full_name.text(),
                password=self.user_password.text(),
                role=str(self.user_role.currentData()),
                is_active=self.user_active.isChecked(),
                permissions=permissions,
            )
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self._reload_users()
        self._clear_user_form()
        QMessageBox.information(self, "تم", "تم حفظ المستخدم والصلاحيات")

    def _delete_user(self) -> None:
        if self.selected_user_id is None:
            QMessageBox.warning(self, "تنبيه", "اختر مستخدمًا أولًا")
            return
        answer = QMessageBox.question(
            self,
            "تأكيد الحذف",
            "هل تريد حذف المستخدم المحدد؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            self.admin_repository.delete_user(self.selected_user_id)
        except (ValueError, PermissionError) as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self._reload_users()
        self._clear_user_form()

    def _confirm_reset(self) -> None:
        first = QMessageBox.warning(
            self,
            "تحذير شديد",
            "سيتم حذف كل بيانات النظام نهائيًا مع الإبقاء على المستخدمين وإعدادات الطباعة.\n"
            "هل تريد الاستمرار؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if first != QMessageBox.Yes:
            return
        dialog = AdminPasswordDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        try:
            self.admin_repository.reset_system(dialog.password())
        except (ValueError, PermissionError) as error:
            QMessageBox.critical(self, "فشل", str(error))
            return
        QMessageBox.information(
            self,
            "تمت إعادة الضبط",
            "تم حذف كل بيانات التشغيل وإرجاع النظام للصفر. أغلق البرنامج وافتحه مرة أخرى.",
        )

    def _reload_printers(self, configured_name: str) -> None:
        names = [printer.printerName() for printer in QPrinterInfo.availablePrinters()]
        if configured_name and configured_name not in names:
            names.insert(0, configured_name)
        self.printer_input.clear()
        self.printer_input.addItems(names or ["Star TSP100"])
        self.printer_input.setCurrentText(configured_name or "Star TSP100")

    def choose_logo(self) -> None:
        source = self._choose_image("اختيار لوجو الفاتورة")
        if source:
            self.logo_source = source
            self._set_preview(self.logo_preview, source)

    def choose_qr(self) -> None:
        source = self._choose_image("اختيار QR الخاص بـ InstaPay")
        if source:
            self.qr_source = source
            self._set_preview(self.qr_preview, source)

    def _choose_image(self, title: str) -> str:
        path, _ = QFileDialog.getOpenFileName(
            self,
            title,
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        return path

    @staticmethod
    def _set_preview(label: QLabel, path: str) -> None:
        pixmap = QPixmap(path)
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText("تعذر عرض الصورة")
            return
        label.setText("")
        label.setPixmap(
            pixmap.scaled(
                label.width() - 8,
                label.height() - 8,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def save(self) -> None:
        try:
            self.repository.save_settings(
                {
                    "company_name": self.company_name_input.text(),
                    "address": self.address_input.text(),
                    "phones": self.phones_input.toPlainText(),
                    "footer": self.footer_input.toPlainText(),
                    "beneficiary_name": self.beneficiary_input.text(),
                    "instapay_handle": self.instapay_input.text(),
                    "printer_name": self.printer_input.currentText(),
                    "paper_width_mm": "80",
                },
                logo_source=self.logo_source,
                qr_source=self.qr_source,
            )
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        self.reload()
        QMessageBox.information(self, "تم", "تم حفظ إعدادات الفاتورة والطباعة")


class AdminPasswordDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("تأكيد كلمة مرور الأدمن")
        self.setMinimumWidth(420)
        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText("اكتب كلمة مرور الأدمن الحالية")
        self.input.returnPressed.connect(self.accept)
        confirm = QPushButton("تأكيد الحذف")
        confirm.setObjectName("dangerButton")
        confirm.clicked.connect(self.accept)
        cancel = QPushButton("إلغاء")
        cancel.setObjectName("secondaryButton")
        cancel.clicked.connect(self.reject)
        actions = QHBoxLayout()
        actions.addWidget(confirm)
        actions.addWidget(cancel)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("أدخل كلمة مرور الأدمن لتنفيذ إعادة الضبط:"))
        layout.addWidget(self.input)
        layout.addLayout(actions)

    def password(self) -> str:
        return self.input.text()
