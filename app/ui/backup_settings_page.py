from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database.connection import Database
from app.services.backup_service import BackupService
from app.ui.appearance import (
    THEME_LABELS,
    AppearanceSettings,
    AppearanceSettingsRepository,
    apply_appearance,
)
from app.ui.print_settings_page import PrintSettingsPage


class BackupPrintSettingsPage(PrintSettingsPage):
    appearance_settings_changed = Signal()

    def __init__(
        self,
        print_repository,
        admin_repository,
        database_path: Path,
    ) -> None:
        super().__init__(print_repository, admin_repository)
        self.database = Database(Path(database_path))
        self.appearance_repository = AppearanceSettingsRepository(self.database)
        self.backup_service = BackupService(Path(database_path))
        self.tabs.insertTab(2, self._build_appearance_tab(), "المظهر")
        self.tabs.insertTab(3, self._build_backup_tab(), "النسخ الاحتياطي")
        self._reload_appearance_settings()
        self._reload_backups()

    def _build_appearance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.theme_input = QComboBox()
        for code, label in THEME_LABELS.items():
            self.theme_input.addItem(label, code)

        self.font_size_input = QSpinBox()
        self.font_size_input.setRange(11, 20)
        self.font_size_input.setSuffix(" px")

        self.interface_scale_input = QSpinBox()
        self.interface_scale_input.setRange(90, 140)
        self.interface_scale_input.setSingleStep(5)
        self.interface_scale_input.setSuffix(" %")

        group = QGroupBox("الثيم وحجم واجهة البرنامج")
        form = QFormLayout(group)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("الثيم", self.theme_input)
        form.addRow("حجم الخط الأساسي", self.font_size_input)
        form.addRow("تكبير العناصر والمسافات", self.interface_scale_input)

        note = QLabel(
            "اختيار «حسب إعداد ويندوز» يجعل البرنامج يستخدم الوضع الفاتح أو الداكن "
            "حسب إعداد النظام عند التشغيل. إعداد التكبير يؤثر على الحقول والأزرار "
            "والتابات والجداول، ولا يغير تنسيق الفواتير المطبوعة."
        )
        note.setWordWrap(True)
        note.setObjectName("subtitleLabel")

        save_button = QPushButton("حفظ وتطبيق المظهر الآن")
        save_button.clicked.connect(self.save_appearance_settings)
        reload_button = QPushButton("إلغاء التعديلات وإعادة التحميل")
        reload_button.setObjectName("secondaryButton")
        reload_button.clicked.connect(self._reload_appearance_settings)

        actions = QHBoxLayout()
        actions.addWidget(save_button)
        actions.addWidget(reload_button)
        actions.addStretch()

        layout.addWidget(group)
        layout.addWidget(note)
        layout.addLayout(actions)
        layout.addStretch()
        return tab

    def _reload_appearance_settings(self) -> None:
        settings = self.appearance_repository.get_settings()
        index = self.theme_input.findData(settings.theme)
        self.theme_input.setCurrentIndex(max(0, index))
        self.font_size_input.setValue(settings.font_size)
        self.interface_scale_input.setValue(settings.scale_percent)

    def save_appearance_settings(self) -> None:
        settings = AppearanceSettings(
            theme=str(self.theme_input.currentData()),
            font_size=int(self.font_size_input.value()),
            scale_percent=int(self.interface_scale_input.value()),
        )
        try:
            self.appearance_repository.save_settings(settings)
        except ValueError as error:
            QMessageBox.warning(self, "تنبيه", str(error))
            return
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_appearance(app, self.appearance_repository)
        self.appearance_settings_changed.emit()
        QMessageBox.information(self, "تم", "تم حفظ وتطبيق إعدادات المظهر")

    def _build_backup_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        title = QLabel("حماية بيانات PipeERP")
        title.setObjectName("sectionTitle")
        explanation = QLabel(
            "يأخذ النظام نسخة تلقائية عند أول تشغيل في كل يوم. يحتفظ بآخر "
            "30 نسخة يومية و12 نسخة شهرية، بينما النسخ اليدوية تبقى حتى تحذفها "
            "بنفسك من فولدر النسخ. قبل أي استرجاع ينشئ النظام نسخة أمان تلقائية."
        )
        explanation.setWordWrap(True)
        explanation.setObjectName("subtitleLabel")

        self.backup_path_label = QLabel()
        self.backup_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.last_backup_label = QLabel()
        self.last_backup_label.setObjectName("subtitleLabel")

        manual_button = QPushButton("إنشاء نسخة احتياطية يدوية الآن")
        manual_button.clicked.connect(self.create_manual_backup)
        open_folder_button = QPushButton("فتح فولدر النسخ الاحتياطية")
        open_folder_button.setObjectName("secondaryButton")
        open_folder_button.clicked.connect(self.open_backup_folder)
        refresh_button = QPushButton("تحديث القائمة")
        refresh_button.setObjectName("secondaryButton")
        refresh_button.clicked.connect(self._reload_backups)

        actions = QHBoxLayout()
        actions.addWidget(manual_button)
        actions.addWidget(open_folder_button)
        actions.addWidget(refresh_button)
        actions.addStretch()

        self.backups_table = QTableWidget(0, 5)
        self.backups_table.setHorizontalHeaderLabels(
            ["التاريخ", "النوع", "اسم الملف", "الحجم", "المسار"]
        )
        self.backups_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.backups_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.backups_table.setSelectionMode(QTableWidget.SingleSelection)

        restore_selected_button = QPushButton("استرجاع النسخة المحددة")
        restore_selected_button.setObjectName("dangerButton")
        restore_selected_button.clicked.connect(self.restore_selected_backup)
        restore_external_button = QPushButton("استرجاع نسخة من ملف خارجي")
        restore_external_button.setObjectName("dangerButton")
        restore_external_button.clicked.connect(self.restore_external_backup)

        restore_actions = QHBoxLayout()
        restore_actions.addWidget(restore_selected_button)
        restore_actions.addWidget(restore_external_button)
        restore_actions.addStretch()

        warning = QLabel(
            "تنبيه: الاسترجاع يستبدل كل البيانات الحالية بمحتوى النسخة المحددة. "
            "سيُغلق البرنامج بعد نجاح الاسترجاع، ثم افتحه مرة أخرى."
        )
        warning.setWordWrap(True)
        warning.setObjectName("subtitleLabel")

        layout.addWidget(title)
        layout.addWidget(explanation)
        layout.addWidget(QLabel("فولدر النسخ:"))
        layout.addWidget(self.backup_path_label)
        layout.addWidget(self.last_backup_label)
        layout.addLayout(actions)
        layout.addWidget(self.backups_table, 1)
        layout.addWidget(warning)
        layout.addLayout(restore_actions)
        return tab

    def _reload_backups(self) -> None:
        if not hasattr(self, "backups_table"):
            return
        backups = self.backup_service.list_backups()
        self.backup_path_label.setText(str(self.backup_service.root_dir))
        self.last_backup_label.setText(
            "آخر نسخة ناجحة: "
            + (
                backups[0].created_at.strftime("%Y-%m-%d %H:%M:%S")
                if backups
                else "لا توجد نسخ حتى الآن"
            )
        )
        self.backups_table.setRowCount(len(backups))
        for row_index, backup in enumerate(backups):
            values = [
                backup.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                backup.category,
                backup.path.name,
                self._format_size(backup.size_bytes),
                str(backup.path),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                if column == 0:
                    item.setData(Qt.UserRole, str(backup.path))
                self.backups_table.setItem(row_index, column, item)
        self.backups_table.resizeColumnsToContents()

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        size = float(size_bytes)
        for unit in ("بايت", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:,.2f} {unit}"
            size /= 1024
        return f"{size_bytes:,} بايت"

    def create_manual_backup(self) -> None:
        try:
            path = self.backup_service.create_backup(category="manual")
        except ValueError as error:
            QMessageBox.warning(self, "فشل النسخ", str(error))
            return
        self._reload_backups()
        QMessageBox.information(
            self,
            "تم النسخ",
            f"تم إنشاء نسخة احتياطية سليمة:\n{path}",
        )

    def open_backup_folder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.backup_service.root_dir)))

    def restore_selected_backup(self) -> None:
        row = self.backups_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "تنبيه", "اختر نسخة من الجدول أولًا")
            return
        item = self.backups_table.item(row, 0)
        if item is None or not item.data(Qt.UserRole):
            QMessageBox.warning(self, "تنبيه", "تعذر تحديد مسار النسخة")
            return
        self._confirm_and_restore(Path(str(item.data(Qt.UserRole))))

    def restore_external_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "اختيار نسخة PipeERP",
            str(self.backup_service.root_dir),
            "PipeERP SQLite Backup (*.sqlite3 *.db);;All Files (*)",
        )
        if path:
            self._confirm_and_restore(Path(path))

    def _confirm_and_restore(self, path: Path) -> None:
        answer = QMessageBox.warning(
            self,
            "تأكيد الاسترجاع",
            "سيتم استبدال جميع البيانات الحالية بمحتوى النسخة التالية:\n"
            f"{path}\n\n"
            "سينشئ النظام نسخة أمان من البيانات الحالية أولًا. هل تريد المتابعة؟",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        try:
            safety_path = self.backup_service.restore_backup(path)
        except ValueError as error:
            QMessageBox.critical(self, "فشل الاسترجاع", str(error))
            return
        QMessageBox.information(
            self,
            "تم الاسترجاع",
            "تم استرجاع النسخة بنجاح.\n"
            f"نسخة الأمان قبل الاسترجاع:\n{safety_path}\n\n"
            "سيتم إغلاق البرنامج الآن. افتحه مرة أخرى لاستخدام البيانات المسترجعة.",
        )
        QApplication.quit()


__all__ = ["BackupPrintSettingsPage"]
