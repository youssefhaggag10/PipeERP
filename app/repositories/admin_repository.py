from __future__ import annotations

from app.database.connection import Database
from app.models.user import User
from app.security.passwords import hash_password, verify_password

PERMISSIONS: tuple[tuple[str, str], ...] = (
    ("dashboard", "الرئيسية"),
    ("crm", "CRM متابعة العملاء"),
    ("products", "الأصناف"),
    ("suppliers", "الموردين"),
    ("customers", "العملاء"),
    ("warehouse", "إعداد المخزن"),
    ("inventory", "رصيد المخزون"),
    ("lots", "أرصدة الدفعات"),
    ("purchases", "المشتريات"),
    ("sales", "المبيعات"),
    ("accounts", "الحسابات"),
    ("stock_card", "كارت الصنف"),
    ("manufacturing", "التصنيع"),
    ("reports", "التقارير"),
    ("settings", "الإعدادات"),
    ("user_management", "إدارة المستخدمين والصلاحيات"),
    ("system_reset", "إعادة ضبط النظام"),
)


class AdminRepository:
    def __init__(self, database: Database, current_user: User) -> None:
        self.database = database
        self.current_user = current_user
        self._ensure_schema()

    @property
    def is_admin(self) -> bool:
        return self.current_user.role.lower() == "admin"

    def _ensure_schema(self) -> None:
        with self.database.session(immediate=True) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS user_permissions(
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    permission_code TEXT NOT NULL,
                    allowed INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY(user_id, permission_code)
                );
                CREATE INDEX IF NOT EXISTS idx_user_permissions_user
                ON user_permissions(user_id, allowed);
                """
            )

    def permission_catalog(self) -> list[dict[str, str]]:
        return [{"code": code, "name": name} for code, name in PERMISSIONS]

    def permissions_for(self, user_id: int | None = None) -> set[str]:
        target_id = int(user_id or self.current_user.id)
        role_row = self.database.fetch_one("SELECT role FROM users WHERE id = ?", (target_id,))
        if role_row is not None and str(role_row["role"]).lower() == "admin":
            return {code for code, _ in PERMISSIONS}
        rows = self.database.fetch_all(
            "SELECT permission_code FROM user_permissions WHERE user_id = ? AND allowed = 1",
            (target_id,),
        )
        return {str(row["permission_code"]) for row in rows}

    def has_permission(self, code: str) -> bool:
        return self.is_admin or code in self.permissions_for()

    def list_users(self) -> list[dict]:
        self._require_admin()
        rows = self.database.fetch_all(
            """
            SELECT id, username, full_name, role, is_active, created_at
            FROM users
            ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, full_name, username
            """
        )
        result = []
        for row in rows:
            item = dict(row)
            item["permissions"] = sorted(self.permissions_for(int(item["id"])))
            result.append(item)
        return result

    def save_user(
        self,
        *,
        username: str,
        full_name: str,
        password: str,
        role: str,
        is_active: bool,
        permissions: set[str],
        user_id: int | None = None,
    ) -> int:
        self._require_admin()
        username = username.strip()
        full_name = full_name.strip()
        role = role.strip().lower() or "employee"
        if not username or not full_name:
            raise ValueError("اسم المستخدم والاسم الكامل مطلوبان")
        if user_id is None and len(password) < 6:
            raise ValueError("كلمة المرور للمستخدم الجديد يجب ألا تقل عن 6 أحرف")
        valid_codes = {code for code, _ in PERMISSIONS}
        permissions = permissions & valid_codes

        with self.database.session(immediate=True) as connection:
            duplicate = connection.execute(
                "SELECT id FROM users WHERE username = ? AND (? IS NULL OR id <> ?)",
                (username, user_id, user_id),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("اسم المستخدم مستخدم بالفعل")

            if user_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO users(username, password_hash, full_name, role, is_active)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (username, hash_password(password), full_name, role, int(is_active)),
                )
                user_id = int(cursor.lastrowid)
            else:
                existing = connection.execute(
                    "SELECT id, role FROM users WHERE id = ?", (user_id,)
                ).fetchone()
                if existing is None:
                    raise ValueError("المستخدم غير موجود")
                if int(user_id) == self.current_user.id and not is_active:
                    raise ValueError("لا يمكن تعطيل المستخدم الحالي")
                connection.execute(
                    """
                    UPDATE users
                    SET username = ?, full_name = ?, role = ?, is_active = ?
                    WHERE id = ?
                    """,
                    (username, full_name, role, int(is_active), user_id),
                )
                if password:
                    if len(password) < 6:
                        raise ValueError("كلمة المرور يجب ألا تقل عن 6 أحرف")
                    connection.execute(
                        "UPDATE users SET password_hash = ? WHERE id = ?",
                        (hash_password(password), user_id),
                    )

            connection.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            if role != "admin":
                connection.executemany(
                    """
                    INSERT INTO user_permissions(user_id, permission_code, allowed)
                    VALUES (?, ?, 1)
                    """,
                    ((user_id, code) for code in sorted(permissions)),
                )
            return int(user_id)

    def delete_user(self, user_id: int) -> None:
        self._require_admin()
        if user_id == self.current_user.id:
            raise ValueError("لا يمكن حذف المستخدم الحالي")
        row = self.database.fetch_one("SELECT role FROM users WHERE id = ?", (user_id,))
        if row is None:
            raise ValueError("المستخدم غير موجود")
        if str(row["role"]).lower() == "admin":
            admin_count = int(
                self.database.fetch_one(
                    "SELECT COUNT(*) AS count FROM users WHERE role = 'admin' AND is_active = 1"
                )["count"]
            )
            if admin_count <= 1:
                raise ValueError("لا يمكن حذف آخر مدير نشط")
        with self.database.session(immediate=True) as connection:
            connection.execute("DELETE FROM user_permissions WHERE user_id = ?", (user_id,))
            connection.execute("DELETE FROM users WHERE id = ?", (user_id,))

    def reset_system(self, admin_password: str) -> None:
        self._require_admin()
        row = self.database.fetch_one(
            "SELECT password_hash FROM users WHERE id = ?", (self.current_user.id,)
        )
        if row is None or not verify_password(admin_password, str(row["password_hash"])):
            raise ValueError("كلمة مرور الأدمن غير صحيحة")

        preserve = {"users", "user_permissions", "settings", "schema_migrations", "sqlite_sequence"}
        with self.database.session(immediate=True) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            tables = [
                str(row[0])
                for row in connection.execute(
                    """
                    SELECT name FROM sqlite_master
                    WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                    """
                ).fetchall()
            ]
            for table in tables:
                if table in preserve:
                    continue
                connection.execute(f'DELETE FROM "{table}"')

            if "sqlite_sequence" in {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }:
                reset_tables = [table for table in tables if table not in preserve]
                for table in reset_tables:
                    connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

            # Restore the single required warehouse and CRM reference data.
            connection.execute(
                "INSERT OR IGNORE INTO warehouses(code, name, is_active) VALUES ('MAIN', 'المصنع', 1)"
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
            connection.execute("PRAGMA foreign_keys = ON")

    def _require_admin(self) -> None:
        if not self.is_admin:
            raise PermissionError("هذه العملية متاحة للأدمن فقط")
