from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


class AppPaths:
    """Resolve writable per-user paths and migrate legacy project data safely."""

    APP_DIR_NAME = "PipeERP"
    DATA_OVERRIDE_ENV = "PIPEERP_DATA_DIR"
    PORTABLE_MODE_ENV = "PIPEERP_PORTABLE_MODE"
    MIGRATION_MARKER = ".legacy-migration-complete"

    @classmethod
    def project_root(cls) -> Path:
        return Path(__file__).resolve().parents[2]

    @classmethod
    def legacy_data_dir(cls) -> Path:
        return cls.project_root() / "data"

    @classmethod
    def user_data_root(cls) -> Path:
        override = os.environ.get(cls.DATA_OVERRIDE_ENV, "").strip()
        if override:
            return Path(override).expanduser().resolve()

        portable = os.environ.get(cls.PORTABLE_MODE_ENV, "").strip().lower()
        if portable in {"1", "true", "yes", "on"}:
            return cls.legacy_data_dir()

        if sys.platform.startswith("win"):
            base = os.environ.get("LOCALAPPDATA", "").strip()
            if base:
                return Path(base) / cls.APP_DIR_NAME
            return Path.home() / "AppData" / "Local" / cls.APP_DIR_NAME

        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / cls.APP_DIR_NAME

        xdg_data_home = os.environ.get("XDG_DATA_HOME", "").strip()
        base = Path(xdg_data_home).expanduser() if xdg_data_home else Path.home() / ".local" / "share"
        return base / cls.APP_DIR_NAME

    @classmethod
    def data_dir(cls) -> Path:
        path = cls.user_data_root()
        path.mkdir(parents=True, exist_ok=True)
        cls._migrate_legacy_data(path)
        return path

    @classmethod
    def logs_dir(cls) -> Path:
        path = cls.data_dir() / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def backups_dir(cls) -> Path:
        path = cls.data_dir() / "backups"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def _migrate_legacy_data(cls, destination: Path) -> None:
        marker = destination / cls.MIGRATION_MARKER
        if marker.exists():
            return

        legacy = cls.legacy_data_dir()
        try:
            if not legacy.exists() or legacy.resolve() == destination.resolve():
                marker.touch(exist_ok=True)
                return
        except OSError:
            return

        database_name = "pipeerp.sqlite3"
        source_database = legacy / database_name
        target_database = destination / database_name
        if source_database.is_file() and not target_database.exists():
            shutil.copy2(source_database, target_database)
            cls._copy_sqlite_sidecars(source_database, target_database)

        source_backups = legacy / "backups"
        target_backups = destination / "backups"
        if source_backups.is_dir():
            target_backups.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_backups, target_backups, dirs_exist_ok=True)

        marker.touch(exist_ok=True)

    @staticmethod
    def _copy_sqlite_sidecars(source_database: Path, target_database: Path) -> None:
        for suffix in ("-wal", "-shm"):
            source = Path(f"{source_database}{suffix}")
            target = Path(f"{target_database}{suffix}")
            if source.is_file() and not target.exists():
                shutil.copy2(source, target)


__all__ = ["AppPaths"]
