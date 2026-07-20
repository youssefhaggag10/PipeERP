from pathlib import Path
from shutil import copy2

from app.core.config import AppConfig
from app.database.connection import Database


class PrintSettingsRepository:
    KEYS = {
        "company_name": "print_company_name",
        "address": "print_address",
        "phones": "print_phones",
        "footer": "print_footer",
        "instapay_handle": "print_instapay_handle",
        "printer_name": "print_printer_name",
        "paper_width_mm": "print_paper_width_mm",
        "logo_path": "print_logo_path",
        "qr_path": "print_qr_path",
        "watermark_enabled": "ui_watermark_enabled",
        "watermark_opacity": "ui_watermark_opacity",
        "watermark_size": "ui_watermark_size",
        "watermark_path": "ui_watermark_path",
    }

    DEFAULTS = {
        "company_name": "ثري إيه بايب - 3A Pipes",
        "address": "المنوفية - سرس الليان",
        "phones": "01229351054\n01035474002",
        "footer": "شكرًا لثقتكم في ثري إيه بايب — جودة تُبنى عليها.",
        "instapay_handle": "ahmed.a351054@instapay",
        "printer_name": "TSP143-(STR_T-001)",
        "paper_width_mm": "80",
        "logo_path": "",
        "qr_path": "",
        "watermark_enabled": "0",
        "watermark_opacity": "8",
        "watermark_size": "35",
        "watermark_path": "",
    }

    def __init__(self, database: Database) -> None:
        self.database = database

    def get_settings(self) -> dict[str, str]:
        db_keys = tuple(self.KEYS.values())
        placeholders = ", ".join("?" for _ in db_keys)
        rows = self.database.fetch_all(
            f"SELECT key, value FROM settings WHERE key IN ({placeholders})",
            db_keys,
        )
        stored = {str(row["key"]): str(row["value"]) for row in rows}
        result = {
            name: stored.get(db_key, self.DEFAULTS[name])
            for name, db_key in self.KEYS.items()
        }
        result["paper_width_mm"] = "80"
        result["logo_path"] = str(
            self._resolve_asset(result["logo_path"], self.default_logo_path())
        )
        result["qr_path"] = str(
            self._resolve_asset(result["qr_path"], self.default_qr_path())
        )
        result["watermark_path"] = str(
            self._resolve_asset(result["watermark_path"], self.default_logo_path())
        )
        return result

    def save_settings(
        self,
        values: dict[str, str],
        *,
        logo_source: str | None = None,
        qr_source: str | None = None,
        watermark_source: str | None = None,
    ) -> None:
        company_name = str(values.get("company_name", "")).strip()
        if not company_name:
            raise ValueError("اسم المنشأة مطلوب في رأس الفاتورة")

        normalized = {
            name: str(values.get(name, self.DEFAULTS[name])).strip()
            for name in self.KEYS
            if name not in {"logo_path", "qr_path", "watermark_path"}
        }
        normalized["company_name"] = company_name
        normalized["paper_width_mm"] = "80"

        try:
            opacity = int(float(normalized.get("watermark_opacity", "8")))
            size = int(float(normalized.get("watermark_size", "35")))
        except ValueError as error:
            raise ValueError("شفافية وحجم العلامة المائية يجب أن يكونا أرقامًا") from error
        if not 1 <= opacity <= 40:
            raise ValueError("شفافية العلامة المائية يجب أن تكون بين 1% و40%")
        if not 10 <= size <= 80:
            raise ValueError("حجم العلامة المائية يجب أن يكون بين 10% و80%")
        normalized["watermark_opacity"] = str(opacity)
        normalized["watermark_size"] = str(size)
        normalized["watermark_enabled"] = (
            "1" if normalized.get("watermark_enabled", "0").lower() in {"1", "true", "yes", "on"} else "0"
        )

        current_assets = self._stored_asset_values()
        if logo_source:
            current_assets["logo_path"] = self._copy_asset(logo_source, "logo")
        if qr_source:
            current_assets["qr_path"] = self._copy_asset(qr_source, "instapay_qr")
        if watermark_source:
            current_assets["watermark_path"] = self._copy_asset(
                watermark_source, "screen_watermark"
            )
        normalized.update(current_assets)

        with self.database.session() as connection:
            connection.executemany(
                "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
                (
                    (self.KEYS[name], value)
                    for name, value in normalized.items()
                ),
            )

    def _stored_asset_values(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in ("logo_path", "qr_path", "watermark_path"):
            row = self.database.fetch_one(
                "SELECT value FROM settings WHERE key = ?",
                (self.KEYS[name],),
            )
            result[name] = "" if row is None else str(row["value"] or "")
        return result

    def _copy_asset(self, source: str, asset_name: str) -> str:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise ValueError("ملف الصورة المحدد غير موجود")
        suffix = source_path.suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".bmp"}:
            raise ValueError("صيغة الصورة غير مدعومة. استخدم PNG أو JPG")
        asset_dir = AppConfig.data_dir() / "print_assets"
        asset_dir.mkdir(parents=True, exist_ok=True)
        destination = asset_dir / f"{asset_name}{suffix}"
        if source_path != destination.resolve():
            copy2(source_path, destination)
        return str(destination.relative_to(AppConfig.data_dir()))

    @staticmethod
    def _resolve_asset(value: str, fallback: Path) -> Path:
        if value:
            path = Path(value).expanduser()
            if not path.is_absolute():
                path = AppConfig.data_dir() / path
            if path.is_file():
                return path
        return fallback

    @staticmethod
    def default_logo_path() -> Path:
        return AppConfig.project_root() / "app" / "assets" / "print" / "default_logo.png"

    @staticmethod
    def default_qr_path() -> Path:
        return (
            AppConfig.project_root()
            / "app"
            / "assets"
            / "print"
            / "default_instapay_qr.png"
        )
