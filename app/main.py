import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from app.core.config import AppConfig
from app.database.connection import Database
from app.database.schema import initialize_database
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.ui.login_dialog import LoginDialog
from app.ui.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(AppConfig.APP_NAME)
    app.setLayoutDirection(Qt.RightToLeft)
    app.setStyleSheet(APP_STYLESHEET)

    database = Database(AppConfig.database_path())
    initialize_database(database)

    try:
        BackupService(database.path).create_automatic_backup_if_due()
    except ValueError as error:
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
    return app.exec()
