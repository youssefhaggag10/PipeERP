import hashlib
import secrets
import unicodedata
from dataclasses import dataclass

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type

MINIMUM_PASSWORD_LENGTH = 12

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65_536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)


@dataclass(frozen=True, slots=True)
class SessionSecrets:
    refresh_token: str
    csrf_token: str


def normalize_username(username: str) -> str:
    normalized = unicodedata.normalize("NFKC", username).strip().casefold()
    if not normalized:
        raise ValueError("اسم المستخدم مطلوب")
    if len(normalized) > 80:
        raise ValueError("اسم المستخدم أطول من الحد المسموح")
    return normalized


def validate_password(password: str) -> None:
    if len(password) < MINIMUM_PASSWORD_LENGTH:
        raise ValueError(f"كلمة المرور يجب ألا تقل عن {MINIMUM_PASSWORD_LENGTH} حرفًا")
    if password.isspace():
        raise ValueError("كلمة المرور غير صالحة")


def hash_password(password: str) -> str:
    validate_password(password)
    return _password_hasher.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        return _password_hasher.verify(encoded_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def password_needs_rehash(encoded_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(encoded_hash)
    except InvalidHashError:
        return True


def generate_session_secrets() -> SessionSecrets:
    return SessionSecrets(
        refresh_token=secrets.token_urlsafe(48),
        csrf_token=secrets.token_urlsafe(32),
    )


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
