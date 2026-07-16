from __future__ import annotations

import logging
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import AppConfig
from app.core.logging_setup import install_exception_hook, setup_logging
from app.database.connection import Database
from app.database.schema import initialize_database
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.services.first_run_service import FirstRunService
from app.ui.first_run_dialog import FirstRunDialog
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET

LOGGER = logging.getLogger("pipeerp")


def _run_smoke_test() -> int:
    database = Database(AppConfig.database_path())
    initialize_database(database)
    first_run = FirstRunService(database)
    if first_run.requires_setup():
        first_run.create_initial_admin(
            username="smoke_admin",
            full_name="Smoke Test Admin",
            password="Smoke-Test-123",
        )
    user = AuthService(database).authenticate("smoke_admin", "Smoke-Test-123")
    if user is None or user.role != "admin":
        raise RuntimeError("PipeERP executable smoke test failed")
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
    app.setStyleSheet(APP_STYLESHEET)

    try:
        database_path = AppConfig.database_path()
        LOGGER.info("Using database path: %s", database_path)
        database = Database(database_path)
        initialize_database(database)

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
        window.showMaximized()
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
