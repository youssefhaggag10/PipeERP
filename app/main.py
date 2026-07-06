import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.config import AppConfig
from app.database.connection import Database
from app.database.schema import initialize_database
from app.services.auth_service import AuthService
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

    auth_service = AuthService(database)
    login_dialog = LoginDialog(auth_service)
    if login_dialog.exec() != LoginDialog.Accepted:
        return 0

    window = MainWindow(current_user=login_dialog.current_user)
    window.show()
    return app.exec()
