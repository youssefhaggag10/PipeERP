import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from argon2.low_level import Type
from jwt import InvalidTokenError

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


@dataclass(frozen=True, slots=True)
class AccessClaims:
    user_id: UUID
    session_id: UUID
    user_version: int


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


def token_matches(token: str, expected_hash: str) -> bool:
    return hmac.compare_digest(hash_token(token), expected_hash)


def create_access_token(
    *,
    user_id: UUID,
    session_id: UUID,
    user_version: int,
    secret_key: str,
    lifetime_minutes: int,
    now: datetime | None = None,
) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "ver": user_version,
        "iat": issued_at,
        "nbf": issued_at,
        "exp": issued_at + timedelta(minutes=lifetime_minutes),
        "iss": "pipeerp",
        "aud": "pipeerp-web",
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_access_token(token: str, secret_key: str) -> AccessClaims | None:
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=["HS256"],
            audience="pipeerp-web",
            issuer="pipeerp",
            options={"require": ["sub", "sid", "ver", "exp", "iat", "nbf"]},
        )
        return AccessClaims(
            user_id=UUID(payload["sub"]),
            session_id=UUID(payload["sid"]),
            user_version=int(payload["ver"]),
        )
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        return None
