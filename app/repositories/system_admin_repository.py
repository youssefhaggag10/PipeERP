from app.repositories.admin_repository import AdminRepository
from app.security.passwords import verify_password


class SystemAdminRepository(AdminRepository):
    """Admin repository with a foreign-key-safe full operational reset."""

    def reset_system(self, admin_password: str) -> None:
        self._require_admin()
        row = self.database.fetch_one(
            "SELECT password_hash FROM users WHERE id = ?", (self.current_user.id,)
        )
        if row is None or not verify_password(admin_password, str(row["password_hash"])):
            raise ValueError("كلمة مرور الأدمن غير صحيحة")

        preserve = {"users", "user_permissions", "settings", "sqlite_sequence"}
        connection = self.database.connect()
        try:
            # foreign_keys must be disabled before the transaction begins.
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute("BEGIN IMMEDIATE")
            tables = [
                str(item[0])
                for item in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchall()
            ]
            reset_tables = [table for table in tables if table not in preserve]
            for table in reset_tables:
                connection.execute(f'DELETE FROM "{table}"')

            sequence_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
            ).fetchone()
            if sequence_exists is not None:
                for table in reset_tables:
                    connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

            connection.execute(
                "INSERT OR IGNORE INTO warehouses(code, name, is_active) "
                "VALUES ('MAIN', 'المصنع', 1)"
            )
            connection.execute(
                "UPDATE warehouses SET name = 'المصنع', is_active = 1 WHERE code = 'MAIN'"
            )
            connection.executemany(
                "INSERT OR IGNORE INTO crm_sources(code, name, sequence) VALUES (?, ?, ?)",
                (
                    ("facebook", "فيسبوك", 10),
                    ("instagram", "إنستجرام", 20),
                    ("whatsapp", "واتساب", 30),
                    ("website", "الموقع", 40),
                    ("paid_ad", "إعلان ممول", 50),
                    ("referral", "ترشيح عميل", 60),
                    ("sales_rep", "مندوب", 70),
                    ("inbound_call", "اتصال وارد", 80),
                    ("exhibition", "معرض", 90),
                    ("other", "مصدر آخر", 100),
                ),
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO crm_stages(code, name, sequence, is_won, is_lost)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    ("new", "عميل جديد", 10, 0, 0),
                    ("not_contacted", "لم يتم التواصل", 20, 0, 0),
                    ("contacted", "تم التواصل", 30, 0, 0),
                    ("interested", "مهتم", 40, 0, 0),
                    ("quotation", "إرسال عرض سعر", 50, 0, 0),
                    ("negotiation", "تفاوض", 60, 0, 0),
                    ("waiting", "انتظار قرار", 70, 0, 0),
                    ("won", "تم البيع", 80, 1, 0),
                    ("postponed", "مؤجل", 90, 0, 0),
                    ("no_answer", "لا يرد", 100, 0, 0),
                    ("not_interested", "غير مهتم", 110, 0, 1),
                    ("invalid_phone", "رقم غير صحيح", 120, 0, 1),
                    ("lost", "خسارة الصفقة", 130, 0, 1),
                ),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.close()
