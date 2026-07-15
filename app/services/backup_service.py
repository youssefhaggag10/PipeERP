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
    DAILY_KEEP = 30
    MONTHLY_KEEP = 12

    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.root_dir = AppConfig.data_dir() / "backups"
        self.daily_dir = self.root_dir / "daily"
        self.monthly_dir = self.root_dir / "monthly"
        self.safety_dir = self.root_dir / "safety-before-restore"
        for path in (self.root_dir, self.daily_dir, self.monthly_dir, self.safety_dir):
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
            raise ValueError("قاعدة البيانات الحالية غير سليمة، لم يتم إنشاء النسخة الاحتياطية")

        now = datetime.now()
        if category == "daily":
            destination_dir = self.daily_dir
        elif category == "monthly":
            destination_dir = self.monthly_dir
        elif category == "safety":
            destination_dir = self.safety_dir
        else:
            destination_dir = self.root_dir

        destination = destination_dir / (
            f"pipeerp_{category}_{now.strftime('%Y-%m-%d_%H-%M-%S')}.sqlite3"