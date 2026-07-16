from app.database.connection import Database
from app.security.passwords import hash_password


class FirstRunService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def requires_setup(self) -> bool:
        row = self.database.fetch_one("SELECT COUNT(*) AS count FROM users")
        return row is None or int(row["count"]) == 0

    def create_initial_admin(
        self,
        *,
        username: str,
        full_name: str,
        password: str,
    ) -> None:
        normalized_username = username.strip()
        normalized_name = full_name.strip()
        if not normalized_username:
            raise ValueError("اسم المستخدم مطلوب")
        if len(normalized_username) < 3:
            raise ValueError("اسم المستخدم يجب ألا يقل عن 3 أحرف")
        if not normalized_name:
            raise ValueError("اسم المدير مطلوب")
        if len(password) < 8:
            raise ValueError("كلمة المرور يجب ألا تقل عن 8 أحرف")

        with self.database.session(immediate=True) as connection:
            user_count = int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])
            if user_count != 0:
                raise ValueError("تم إعداد المستخدم الأول بالفعل")
            connection.execute(
                """
                INSERT INTO users(username, password_hash, full_name, role, is_active)
                VALUES (?, ?, ?, 'admin', 1)
                """,
                (normalized_username, hash_password(password), normalized_name),
            )


__all__ = ["FirstRunService"]
