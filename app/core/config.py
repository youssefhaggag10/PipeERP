from pathlib import Path

from app.core.app_paths import AppPaths


class AppConfig:
    APP_NAME = "PipeERP"
    APP_VERSION = "0.2.0"
    APP_DISPLAY_NAME_AR = "3A PIPE"
    COMPANY_NAME = "3A PIPE"
    DATA_DIR_NAME = "data"
    DATABASE_FILE_NAME = "pipeerp.sqlite3"

    @classmethod
    def project_root(cls) -> Path:
        return AppPaths.project_root()

    @classmethod
    def data_dir(cls) -> Path:
        return AppPaths.data_dir()

    @classmethod
    def logs_dir(cls) -> Path:
        return AppPaths.logs_dir()

    @classmethod
    def database_path(cls) -> Path:
        return cls.data_dir() / cls.DATABASE_FILE_NAME
