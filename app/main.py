from __future__ import annotations

import logging
import os
import secrets
import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import AppConfig
from app.core.logging_setup import install_exception_hook, setup_logging
from app.database.connection import Database
from app.database.schema import initialize_database
from app.repositories.print_settings_repository import PrintSettingsRepository
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.services.first_run_service import FirstRunService
from app.ui.appearance import AppearanceSettingsRepository, apply_appearance
from app.ui.first_run_dialog import FirstRunDialog
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET
from app.ui.table_readability import install_global_table_configuration

LOGGER = logging.getLogger("pipeerp")


def _run_smoke_test() -> int:
    database = Database(AppConfig.database_path())
    initialize_database(database)
    first_run = FirstRunService(database)

    if first_run.requires_setup():
        smoke_username = f"smoke_{secrets.token_hex(8)}"
        smoke_credential = secrets.token_urlsafe(32)
        first_run.create_initial_admin(
            username=smoke_username,
            full_name="Smoke Test Admin",
            password=smoke_credential,
        )
        user = AuthService(database).authenticate(smoke_username, smoke_credential)
        if user is None or user.role != "admin":
            raise RuntimeError("PipeERP executable smoke-test authentication failed")
    else:
        admin = database.fetch_one(
            "SELECT id FROM users WHERE role = 'admin' AND is_active = 1 LIMIT 1"
        )
        if admin is None:
            raise RuntimeError("PipeERP executable smoke test found no active administrator")

    LOGGER.info("PipeERP executable smoke test passed")
    return 0


def main() -> int:
    log_path = setup_logging()
    install_exception_hook()

    if os.environ.get("PIPEERP_SMOKE_TEST", "").strip() == "1":
        try:
            return _run_smoke_test()
        except Exception:
            LOGGER.exception("Executable smoke test failed")
            return 1

    app = QApplication(sys.argv)
    app.setApplicationName(AppConfig.APP_NAME)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)
    install_global_table_configuration(app)
    app.setWindowIcon(QIcon(str(PrintSettingsRepository.default_logo_path())))

    try:
        database_path = AppConfig.database_path()
        LOGGER.info("Using database path: %s", database_path)
        database = Database(database_path)
        initialize_database(database)
        apply_appearance(app, AppearanceSettingsRepository(database))

        first_run_service = FirstRunService(database)
        if first_run_service.requires_setup():
            setup_dialog = FirstRunDialog(first_run_service)
            if setup_dialog.exec() != FirstRunDialog.Accepted:
                LOGGER.info("Initial administrator setup was cancelled")
                return 0
        try:
            BackupService(database.path).create_automatic_backup_if_due()
        except ValueError as error:
            LOGGER.exception("Automatic backup failed")
            QMessageBox.warning(
                None,
                "تنبيه النسخ الاحتياطي",
                "تعذر إنشاء النسخة الاحتياطية التلقائية اليوم، لكن يمكن متابعة "
                f"استخدام البرنامج.\n\n{error}",
            )

        auth_service = AuthService(database)
        login_dialog = LoginDialog(auth_service)
        if login_dialog.exec() != LoginDialog.Accepted:
            return 0
        if login_dialog.current_user is None:
            return 0

        window = MainWindow(login_dialog.current_user, database)
        window.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        window.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        window.setMinimumSize(900, 600)
        window.setMaximumSize(16777215, 16777215)
        window.showFullScreen()
        exit_code = app.exec()
        LOGGER.info("PipeERP closed with exit code %s", exit_code)
        return exit_code
    except Exception as error:
        LOGGER.exception("Fatal application startup error")
        QMessageBox.critical(
            None,
            "تعذر تشغيل البرنامج",
            "حدث خطأ غير متوقع أثناء تشغيل PipeERP.\n\n"
            f"تم تسجيل التفاصيل في:\n{log_path}\n\n"
            f"الخطأ: {error}",
        )
        return 1
