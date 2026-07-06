from app.database.connection import Database
from app.models.user import User
from app.security.passwords import verify_password


class AuthService:
    def __init__(self, database: Database) -> None:
        self.database = database

    def authenticate(self, username: str, password: str) -> User | None:
        row = self.database.fetch_one(
            """
            SELECT id, username, password_hash, full_name, role
            FROM users
            WHERE username = ? AND is_active = 1
            """,
            (username.strip(),),
        )
        if row is None:
            return None
        if not verify_password(password, row["password_hash"]):
            return None
        return User(
            id=row["id"],
            username=row["username"],
            full_name=row["full_name"],
            role=row["role"],
        )
