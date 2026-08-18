from app.modules.identity.permissions import SYSTEM_ROLES, PermissionCode
from app.modules.identity.security import (
    generate_session_secrets,
    hash_password,
    hash_token,
    normalize_username,
    password_needs_rehash,
    validate_password,
    verify_password,
)


def test_username_normalization_is_stable_and_case_insensitive() -> None:
    assert normalize_username("  Factory.Admin  ") == "factory.admin"


def test_password_hash_uses_argon2id_and_verifies_without_exposing_password() -> None:
    encoded = hash_password("A-secure-password-2026")

    assert encoded.startswith("$argon2id$")
    assert "A-secure-password-2026" not in encoded
    assert verify_password("A-secure-password-2026", encoded)
    assert not verify_password("wrong-password", encoded)
    assert not password_needs_rehash(encoded)


def test_invalid_hash_never_authenticates() -> None:
    assert not verify_password("any-password", "not-an-argon-hash")
    assert password_needs_rehash("not-an-argon-hash")


def test_password_policy_rejects_short_values() -> None:
    try:
        validate_password("short")
    except ValueError as exc:
        assert "12" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_session_secrets_are_random_and_only_hashes_are_persisted() -> None:
    first = generate_session_secrets()
    second = generate_session_secrets()

    assert first != second
    assert len(hash_token(first.refresh_token)) == 64
    assert first.refresh_token not in hash_token(first.refresh_token)


def test_system_admin_role_receives_every_identity_permission() -> None:
    name_ar, permissions = SYSTEM_ROLES["system_admin"]

    assert name_ar == "مدير النظام"
    assert permissions == set(PermissionCode)
    assert PermissionCode.ROLES_MANAGE not in SYSTEM_ROLES["operations_manager"][1]
