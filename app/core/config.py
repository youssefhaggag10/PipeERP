from pathlib import Path


class AppConfig:
    APP_NAME = "PipeERP"
    APP_DISPLAY_NAME_AR = "3A PIPE"
    COMPANY_NAME = "3A PIPE"
    DATA_DIR_NAME = "data"
    DATABASE_FILE_NAME = "pipeerp.sqlite3"

    @classmethod
    def project_root(cls) -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def data_dir(cls) -> Path:
        path = cls.project_root() / cls.DATA_DIR_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def database_path(cls) -> Path:
        return cls.data_dir() / cls.DATABASE_FILE_NAME
