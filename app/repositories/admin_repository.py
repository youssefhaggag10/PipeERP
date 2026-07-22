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
    ("system_reset", "تصفير حركات النظام"),
)


# These tables contain reusable setup data, not day-to-day business movements.
# A system reset must leave them intact.
MASTER_DATA_TABLES = frozenset(
    {
        "users",
        "user_permissions",
        "settings",
        "schema_migrations",
        "warehouses",
        "partners",
        "products",
        "manufacturing_recipes",
        "manufacturing_recipe_outputs",
        "manufacturing_recipe_components",
        "financial_accounts",
        "crm_sources",
        "crm_stages",
    }
)

# Keep this deletion list explicit: resetting data is destructive, so an
# unfamiliar future table must never be deleted until it is deliberately
# classified as operational or master data.
OPERATIONAL_DATA_TABLES = frozenset(
    {
        "crm_activities",
        "crm_leads",
        "customer_account_adjustments",
        "financial_account_adjustments",
        "financial_account_transfers",
        "finished_good_weight_layers",
        "inventory_cost_allocations",
        "inventory_moves",
        "invoice_return_lines",
        "invoice_returns",
        "lots",
        "manufacturing_completion_outputs",
        "manufacturing_completion_summaries",
        "manufacturing_mix_adjustments",
        "manufacturing_order_materials",
        "manufacturing_order_outputs",
        "manufacturing_orders",
        "manufacturing_run_events",
        "manufacturing_run_materials",
        "manufacturing_run_outputs",
        "manufacturing_runs",
        "payment_allocations",
        "payment_reversals",
        "payment_transactions",
        "purchase_invoices",
        "purchase_order_lines",
        "purchase_orders",
        "return_refunds",
        "sales_invoices",
        "sales_order_lines",
        "sales_orders",
        "sales_quotation_lines",
        "sales_quotations",
        "sales_weight_card_lines",
        "sales_weight_cards",
        "sales_weight_inventory_allocations",
    }
)


def _clear_operational_data(database: Database) -> None:
    """Delete transactions atomically while preserving reusable master data."""
    connection = database.connect()
    try:
        # SQLite only applies this pragma outside an active transaction.
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("BEGIN IMMEDIATE")
        tables = [
            str(row[0])
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                """
            ).fetchall()
        ]
        reset_tables = [table for table in tables if table in OPERATIONAL_DATA_TABLES]
        for table in reset_tables:
            connection.execute(f'DELETE FROM "{table}"')

        sequence_exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        ).fetchone()
        if sequence_exists is not None:
            for table in reset_tables:
                connection.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))

        # This value is calculated from purchase/inventory history, which has
        # just been cleared. Keep the recipe itself but discard the stale cost.
        recipe_columns = {
            str(row[1])
            for row in connection.execute(
                "PRAGMA table_info(manufacturing_recipes)"
            ).fetchall()
        }
        if "estimated_scrap_unit_cost" in recipe_columns:
            connection.execute(
                "UPDATE manufacturing_recipes SET estimated_scrap_unit_cost = 0"
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.close()


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

        _clear_operational_data(self.database)

    def _require_admin(self) -> None:
        if not self.is_admin:
            raise PermissionError("هذه العملية متاحة للأدمن فقط")
