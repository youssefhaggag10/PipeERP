from app.repositories.admin_repository import AdminRepository, _clear_operational_data
from app.security.passwords import verify_password


class SystemAdminRepository(AdminRepository):
    """Admin repository with a foreign-key-safe operational-data reset."""

    def reset_system(self, admin_password: str) -> None:
        self._require_admin()
        row = self.database.fetch_one(
            "SELECT password_hash FROM users WHERE id = ?", (self.current_user.id,)
        )
        if row is None or not verify_password(admin_password, str(row["password_hash"])):
            raise ValueError("كلمة مرور الأدمن غير صحيحة")

        _clear_operational_data(self.database)
