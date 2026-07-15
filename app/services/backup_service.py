from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from shutil import copy2

from app.core.config import AppConfig


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: datetime
    size_bytes: int
    category: str


class BackupService:
    """Creates verified SQLite backups and restores them safely.

    Policy:
    - One automatic daily backup at the first application start of the day.
    - One automatic monthly snapshot copied from the first successful daily backup
      created in that month.
    - Keep the latest 30 daily backups and 12 monthly backups.
    - Manual backups are retained until the user deletes them outside the app.
    - A safety backup is always created immediately before restoring a database.
    """

    DAILY_KEEP = 30
    MONTHLY_KEEP = 12

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.root_dir = AppConfig.data_dir() / "backups"
        self.daily_dir = self.root_dir / "daily"
        self.monthly_dir = self.root_dir / "monthly"
        self.manual_dir = self.root_dir / "manual"
        self.safety_dir = self.root_dir / "safety-before-restore"
        for path in (
            self.root_dir,
            self.daily_dir,
            self.monthly_dir,
            self.manual_dir,
            self.safety_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def database_is_healthy(self, path: Path | None = None) -> bool:
        target = Path(path or self.database_path)
        if not target.is_file():
            return False
        try:
            with sqlite3.connect(target) as connection:
                row = connection.execute("PRAGMA integrity_check").fetchone()
            return bool(row and str(row[0]).lower() == "ok")
        except sqlite3.Error:
            return False

    def create_backup(self, *, category: str = "manual") -> Path:
        if not self.database_is_healthy():
            raise ValueError(
                "قاعدة البيانات الحالية غير سليمة، لم يتم إنشاء النسخة الاحتياطية"
            )

        now = datetime.now()
        destination_dir = {
            "daily": self.daily_dir,
            "monthly": self.monthly_dir,
            "manual": self.manual_dir,
            "safety": self.safety_dir,
        }.get(category, self.manual_dir)
        destination = destination_dir / (
            f"pipeerp_{category}_{now.strftime('%Y-%m-%d_%H-%M-%S')}.sqlite3"
        )

        try:
            with sqlite3.connect(self.database_path) as source:
                with sqlite3.connect(destination) as target:
                    source.backup(target)
        except sqlite3.Error as error:
            destination.unlink(missing_ok=True)
            raise ValueError(f"فشل إنشاء النسخة الاحتياطية: {error}") from error

        if not self.database_is_healthy(destination):
            destination.unlink(missing_ok=True)
            raise ValueError("تم إنشاء ملف النسخة لكنه لم يجتز فحص السلامة")

        if category == "daily":
            self._ensure_monthly_snapshot(destination, now)
        self.cleanup_retention()
        return destination

    def create_automatic_backup_if_due(self) -> Path | None:
        today_prefix = f"pipeerp_daily_{datetime.now().strftime('%Y-%m-%d')}_"
        if any(path.name.startswith(today_prefix) for path in self.daily_dir.glob("*.sqlite3")):
            return None
        return self.create_backup(category="daily")

    def _ensure_monthly_snapshot(self, daily_backup: Path, now: datetime) -> None:
        month_prefix = f"pipeerp_monthly_{now.strftime('%Y-%m')}_"
        if any(
            path.name.startswith(month_prefix)
            for path in self.monthly_dir.glob("*.sqlite3")
        ):
            return
        destination = self.monthly_dir / (
            f"pipeerp_monthly_{now.strftime('%Y-%m-%d_%H-%M-%S')}.sqlite3"
        )
        copy2(daily_backup, destination)
        if not self.database_is_healthy(destination):
            destination.unlink(missing_ok=True)
            raise ValueError("فشل فحص سلامة النسخة الشهرية")

    def cleanup_retention(self) -> None:
        self._keep_latest(self.daily_dir, self.DAILY_KEEP)
        self._keep_latest(self.monthly_dir, self.MONTHLY_KEEP)

    @staticmethod
    def _keep_latest(directory: Path, keep: int) -> None:
        files = sorted(
            directory.glob("*.sqlite3"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old_file in files[keep:]:
            old_file.unlink(missing_ok=True)

    def list_backups(self) -> list[BackupInfo]:
        result: list[BackupInfo] = []
        categories = {
            "يومية تلقائية": self.daily_dir,
            "شهرية": self.monthly_dir,
            "يدوية": self.manual_dir,
            "أمان قبل الاسترجاع": self.safety_dir,
        }
        for category, directory in categories.items():
            for path in directory.glob("*.sqlite3"):
                stat = path.stat()
                result.append(
                    BackupInfo(
                        path=path,
                        created_at=datetime.fromtimestamp(stat.st_mtime),
                        size_bytes=stat.st_size,
                        category=category,
                    )
                )
        return sorted(result, key=lambda item: item.created_at, reverse=True)

    def restore_backup(self, source_path: Path) -> Path:
        source = Path(source_path).expanduser().resolve()
        if not source.is_file():
            raise ValueError("ملف النسخة الاحتياطية غير موجود")
        if source == self.database_path.resolve():
            raise ValueError("الملف المحدد هو قاعدة البيانات الحالية بالفعل")
        if not self.database_is_healthy(source):
            raise ValueError("النسخة المحددة غير سليمة ولا يمكن استرجاعها")

        safety_backup = self.create_backup(category="safety")
        temporary = self.database_path.with_suffix(".restore-temp.sqlite3")
        temporary.unlink(missing_ok=True)
        copy2(source, temporary)
        if not self.database_is_healthy(temporary):
            temporary.unlink(missing_ok=True)
            raise ValueError("تعذر التحقق من الملف المؤقت قبل الاسترجاع")

        try:
            temporary.replace(self.database_path)
            self._remove_sqlite_sidecars()
        except OSError as error:
            temporary.unlink(missing_ok=True)
            raise ValueError(f"فشل استبدال قاعدة البيانات: {error}") from error

        if not self.database_is_healthy():
            copy2(safety_backup, self.database_path)
            self._remove_sqlite_sidecars()
            raise ValueError(
                "فشل فحص قاعدة البيانات بعد الاسترجاع وتمت إعادة نسخة الأمان"
            )
        return safety_backup

    def _remove_sqlite_sidecars(self) -> None:
        for suffix in ("-wal", "-shm", "-journal"):
            Path(f"{self.database_path}{suffix}").unlink(missing_ok=True)


__all__ = ["BackupInfo", "BackupService"]
