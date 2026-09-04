from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.modules.identity.models import (
    AuditLog,
    AuthSession,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.modules.identity.permissions import PERMISSION_NAMES_AR, SYSTEM_ROLES, PermissionCode
from app.modules.identity.schemas import RoleView, UserView
from app.modules.identity.security import (
    SessionSecrets,
    decode_access_token,
    generate_session_secrets,
    hash_password,
    hash_token,
    normalize_username,
    password_needs_rehash,
    token_matches,
    verify_password,
)

MAX_IP_FAILURES = 20
IP_FAILURE_WINDOW = timedelta(minutes=5)
_DUMMY_PASSWORD_HASH = hash_password("invalid-account-password-placeholder")


class IdentityError(Exception):
    pass


class AuthenticationFailed(IdentityError):
    pass


class RateLimitExceeded(IdentityError):
    pass


class IdentityConflict(IdentityError):
    pass


class IdentityNotFound(IdentityError):
    pass


class ProtectedOperation(IdentityError):
    pass


@dataclass(frozen=True, slots=True)
class ClientContext:
    ip_address: str | None
    user_agent: str | None
    request_id: str | None


@dataclass(frozen=True, slots=True)
class Principal:
    user: User
    auth_session: AuthSession
    roles: frozenset[str]
    permissions: frozenset[PermissionCode]


@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    principal: Principal
    secrets: SessionSecrets


def utc_now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def add_audit(
    db: Session,
    *,
    event_type: str,
    entity_type: str,
    outcome: str,
    client: ClientContext,
    actor_user_id: UUID | None = None,
    entity_id: str | None = None,
    before_state: dict[str, object] | None = None,
    after_state: dict[str, object] | None = None,
    details: dict[str, object] | None = None,
    now: datetime | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            outcome=outcome,
            request_id=client.request_id,
            ip_address=client.ip_address,
            user_agent=client.user_agent,
            before_state=before_state,
            after_state=after_state,
            details=details,
            created_at=now or utc_now(),
        )
    )


def seed_identity_reference_data(db: Session) -> None:
    permissions: dict[PermissionCode, Permission] = {}
    for code in PermissionCode:
        permission = db.scalar(select(Permission).where(Permission.code == code.value))
        if permission is None:
            module, action = code.value.split(".", maxsplit=1)
            permission = Permission(
                code=code.value,
                module=module,
                action=action,
                name_ar=PERMISSION_NAMES_AR[code],
                description="",
            )
            db.add(permission)
            db.flush()
        permissions[code] = permission

    for role_code, (name_ar, role_permissions) in SYSTEM_ROLES.items():
        role = db.scalar(select(Role).where(Role.code == role_code))
        if role is None:
            role = Role(code=role_code, name_ar=name_ar, description="", is_system=True)
            db.add(role)
            db.flush()
        else:
            role.name_ar = name_ar
            role.is_system = True
        db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
        db.add_all(
            RolePermission(role_id=role.id, permission_id=permissions[code].id)
            for code in role_permissions
        )


def create_initial_admin(
    db: Session,
    *,
    username: str,
    display_name: str,
    password: str,
    client: ClientContext,
) -> User:
    if db.scalar(select(func.count(User.id))) != 0:
        raise IdentityConflict("تم إنشاء مستخدمين بالفعل؛ أمر التأسيس يعمل مرة واحدة فقط")
    seed_identity_reference_data(db)
    admin_role = db.scalar(select(Role).where(Role.code == "system_admin"))
    if admin_role is None:
        raise RuntimeError("تعذر إنشاء دور مدير النظام")
    now = utc_now()
    user = User(
        username=username.strip(),
        normalized_username=normalize_username(username),
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=False,
        failed_login_attempts=0,
        version=1,
    )
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=admin_role.id, assigned_at=now))
    add_audit(
        db,
        actor_user_id=user.id,
        event_type="identity.bootstrap",
        entity_type="user",
        entity_id=str(user.id),
        outcome="success",
        client=client,
        after_state={"username": user.username, "roles": ["system_admin"]},
        now=now,
    )
    return user


def _role_codes(db: Session, user_id: UUID) -> frozenset[str]:
    rows = db.scalars(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
    )
    return frozenset(rows)


def _permission_codes(db: Session, user_id: UUID) -> frozenset[PermissionCode]:
    rows = db.scalars(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .where(UserRole.user_id == user_id)
        .distinct()
    )
    return frozenset(PermissionCode(code) for code in rows)


def build_principal(db: Session, user: User, auth_session: AuthSession) -> Principal:
    return Principal(
        user=user,
        auth_session=auth_session,
        roles=_role_codes(db, user.id),
        permissions=_permission_codes(db, user.id),
    )


def user_view(db: Session, user: User) -> UserView:
    return UserView(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        is_active=user.is_active,
        must_change_password=user.must_change_password,
        roles=sorted(_role_codes(db, user.id)),
        permissions=sorted(_permission_codes(db, user.id), key=str),
    )


def _ip_is_rate_limited(db: Session, client: ClientContext, now: datetime) -> bool:
    if client.ip_address is None:
        return False
    failures = db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.event_type == "auth.login",
            AuditLog.outcome == "failure",
            AuditLog.ip_address == client.ip_address,
            AuditLog.created_at >= now - IP_FAILURE_WINDOW,
        )
    )
    return (failures or 0) >= MAX_IP_FAILURES


def authenticate(
    db: Session,
    *,
    username: str,
    password: str,
    client: ClientContext,
    session_hours: int,
    max_attempts: int,
    lock_minutes: int,
    now: datetime | None = None,
) -> AuthenticationResult:
    current_time = now or utc_now()
    if _ip_is_rate_limited(db, client, current_time):
        add_audit(
            db,
            event_type="auth.login",
            entity_type="session",
            outcome="denied",
            client=client,
            details={"reason": "ip_rate_limit"},
            now=current_time,
        )
        raise RateLimitExceeded

    normalized = normalize_username(username)
    user = db.scalar(
        select(User).where(User.normalized_username == normalized).with_for_update()
    )
    if user is None:
        verify_password(password, _DUMMY_PASSWORD_HASH)
        add_audit(
            db,
            event_type="auth.login",
            entity_type="session",
            outcome="failure",
            client=client,
            details={"reason": "invalid_credentials"},
            now=current_time,
        )
        raise AuthenticationFailed

    password_valid = verify_password(password, user.password_hash)
    locked = user.locked_until is not None and _as_utc(user.locked_until) > current_time
    if not user.is_active or locked or not password_valid:
        if not password_valid and user.is_active and not locked:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= max_attempts:
                user.locked_until = current_time + timedelta(minutes=lock_minutes)
        add_audit(
            db,
            actor_user_id=user.id,
            event_type="auth.login",
            entity_type="session",
            outcome="failure",
            client=client,
            details={"reason": "invalid_credentials"},
            now=current_time,
        )
        raise AuthenticationFailed

    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = current_time
    secrets = generate_session_secrets()
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_token(secrets.refresh_token),
        csrf_token_hash=hash_token(secrets.csrf_token),
        created_at=current_time,
        expires_at=current_time + timedelta(hours=session_hours),
        last_seen_at=current_time,
        ip_address=client.ip_address,
        user_agent=client.user_agent,
    )
    db.add(auth_session)
    db.flush()
    add_audit(
        db,
        actor_user_id=user.id,
        event_type="auth.login",
        entity_type="session",
        entity_id=str(auth_session.id),
        outcome="success",
        client=client,
        now=current_time,
    )
    return AuthenticationResult(build_principal(db, user, auth_session), secrets)


def principal_from_access_token(
    db: Session,
    *,
    token: str,
    secret_key: str,
    now: datetime | None = None,
) -> Principal | None:
    claims = decode_access_token(token, secret_key)
    if claims is None:
        return None
    current_time = now or utc_now()
    row = db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(AuthSession.id == claims.session_id, User.id == claims.user_id)
    ).one_or_none()
    if row is None:
        return None
    user, auth_session = row
    if (
        not user.is_active
        or user.version != claims.user_version
        or auth_session.revoked_at is not None
        or _as_utc(auth_session.expires_at) <= current_time
    ):
        return None
    return build_principal(db, user, auth_session)


def refresh_authentication(
    db: Session,
    *,
    refresh_token: str,
    csrf_token: str,
    client: ClientContext,
    now: datetime | None = None,
) -> AuthenticationResult:
    current_time = now or utc_now()
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == hash_token(refresh_token))
        .with_for_update()
    )
    if auth_session is None:
        raise AuthenticationFailed
    user = db.get(User, auth_session.user_id)
    valid = (
        user is not None
        and user.is_active
        and auth_session.revoked_at is None
        and _as_utc(auth_session.expires_at) > current_time
        and token_matches(csrf_token, auth_session.csrf_token_hash)
    )
    if not valid or user is None:
        add_audit(
            db,
            actor_user_id=auth_session.user_id,
            event_type="auth.refresh",
            entity_type="session",
            entity_id=str(auth_session.id),
            outcome="denied",
            client=client,
            now=current_time,
        )
        raise AuthenticationFailed
    secrets = generate_session_secrets()
    auth_session.refresh_token_hash = hash_token(secrets.refresh_token)
    auth_session.csrf_token_hash = hash_token(secrets.csrf_token)
    auth_session.last_seen_at = current_time
    add_audit(
        db,
        actor_user_id=user.id,
        event_type="auth.refresh",
        entity_type="session",
        entity_id=str(auth_session.id),
        outcome="success",
        client=client,
        now=current_time,
    )
    return AuthenticationResult(build_principal(db, user, auth_session), secrets)


def revoke_session(
    db: Session,
    *,
    refresh_token: str,
    csrf_token: str,
    client: ClientContext,
    now: datetime | None = None,
) -> None:
    current_time = now or utc_now()
    auth_session = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_token_hash == hash_token(refresh_token))
        .with_for_update()
    )
    if auth_session is None or not token_matches(csrf_token, auth_session.csrf_token_hash):
        raise AuthenticationFailed
    auth_session.revoked_at = current_time
    add_audit(
        db,
        actor_user_id=auth_session.user_id,
        event_type="auth.logout",
        entity_type="session",
        entity_id=str(auth_session.id),
        outcome="success",
        client=client,
        now=current_time,
    )


def change_own_password(
    db: Session,
    *,
    principal: Principal,
    current_password: str,
    new_password: str,
    client: ClientContext,
) -> None:
    user = db.scalar(select(User).where(User.id == principal.user.id).with_for_update())
    if user is None or not verify_password(current_password, user.password_hash):
        add_audit(
            db,
            actor_user_id=principal.user.id,
            event_type="identity.password.change",
            entity_type="user",
            entity_id=str(principal.user.id),
            outcome="failure",
            client=client,
            details={"reason": "invalid_current_password"},
        )
        raise AuthenticationFailed
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.version += 1
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    add_audit(
        db,
        actor_user_id=user.id,
        event_type="identity.password.change",
        entity_type="user",
        entity_id=str(user.id),
        outcome="success",
        client=client,
    )


def validate_csrf(principal: Principal, header_token: str | None, cookie_token: str | None) -> bool:
    if header_token is None or cookie_token is None:
        return False
    return token_matches(header_token, principal.auth_session.csrf_token_hash) and token_matches(
        cookie_token,
        principal.auth_session.csrf_token_hash,
    )


def list_users(db: Session) -> list[UserView]:
    return [user_view(db, user) for user in db.scalars(select(User).order_by(User.username))]


def _resolve_roles(db: Session, role_codes: set[str]) -> list[Role]:
    roles = list(db.scalars(select(Role).where(Role.code.in_(role_codes))))
    if {role.code for role in roles} != role_codes:
        raise IdentityNotFound("يوجد دور غير معروف")
    return roles


def create_user(
    db: Session,
    *,
    username: str,
    display_name: str,
    password: str,
    role_codes: set[str],
    must_change_password: bool,
    actor: Principal,
    client: ClientContext,
) -> User:
    normalized = normalize_username(username)
    if db.scalar(select(User.id).where(User.normalized_username == normalized)) is not None:
        raise IdentityConflict("اسم المستخدم مستخدم بالفعل")
    roles = _resolve_roles(db, role_codes)
    now = utc_now()
    user = User(
        username=username.strip(),
        normalized_username=normalized,
        display_name=display_name.strip(),
        password_hash=hash_password(password),
        is_active=True,
        must_change_password=False,
        failed_login_attempts=0,
        version=1,
    )
    db.add(user)
    db.flush()
    db.add_all(
        UserRole(
            user_id=user.id,
            role_id=role.id,
            assigned_at=now,
            assigned_by_user_id=actor.user.id,
        )
        for role in roles
    )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="identity.user.create",
        entity_type="user",
        entity_id=str(user.id),
        outcome="success",
        client=client,
        after_state={"username": user.username, "roles": sorted(role_codes)},
        now=now,
    )
    return user


def update_user(
    db: Session,
    *,
    target_user_id: UUID,
    actor: Principal,
    client: ClientContext,
    display_name: str | None,
    is_active: bool | None,
    role_codes: set[str] | None,
    new_password: str | None,
    must_change_password: bool | None,
) -> User:
    user = db.get(User, target_user_id)
    if user is None:
        raise IdentityNotFound("المستخدم غير موجود")
    if user.id == actor.user.id and (is_active is False or role_codes is not None):
        raise ProtectedOperation("لا يمكنك تعطيل حسابك أو تعديل أدوارك بنفسك")
    before = {
        "display_name": user.display_name,
        "is_active": user.is_active,
        "roles": sorted(_role_codes(db, user.id)),
    }
    security_changed = False
    if display_name is not None:
        user.display_name = display_name.strip()
    if is_active is not None and is_active != user.is_active:
        user.is_active = is_active
        security_changed = True
    if new_password is not None:
        user.password_hash = hash_password(new_password)
        security_changed = True
    if must_change_password is not None:
        user.must_change_password = False
    if role_codes is not None:
        roles = _resolve_roles(db, role_codes)
        db.execute(delete(UserRole).where(UserRole.user_id == user.id))
        now = utc_now()
        db.add_all(
            UserRole(
                user_id=user.id,
                role_id=role.id,
                assigned_at=now,
                assigned_by_user_id=actor.user.id,
            )
            for role in roles
        )
        security_changed = True
    if security_changed:
        user.version += 1
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
    db.flush()
    after = {
        "display_name": user.display_name,
        "is_active": user.is_active,
        "roles": sorted(_role_codes(db, user.id)),
    }
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="identity.user.update",
        entity_type="user",
        entity_id=str(user.id),
        outcome="success",
        client=client,
        before_state=before,
        after_state=after,
    )
    return user


def delete_user(
    db: Session,
    *,
    target_user_id: UUID,
    actor: Principal,
    client: ClientContext,
) -> None:
    user = db.get(User, target_user_id)
    if user is None:
        raise IdentityNotFound("المستخدم غير موجود")
    if user.id == actor.user.id:
        raise ProtectedOperation("لا يمكنك حذف حسابك الحالي")
    before = {
        "username": user.username,
        "display_name": user.display_name,
        "is_active": user.is_active,
        "roles": sorted(_role_codes(db, user.id)),
    }
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="identity.user.delete",
        entity_type="user",
        entity_id=str(user.id),
        outcome="success",
        client=client,
        before_state=before,
    )
    db.delete(user)


def list_roles(db: Session) -> list[RoleView]:
    result: list[RoleView] = []
    for role in db.scalars(select(Role).order_by(Role.is_system.desc(), Role.name_ar)):
        codes = db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
        result.append(
            RoleView(
                id=role.id,
                code=role.code,
                name_ar=role.name_ar,
                description=role.description,
                is_system=role.is_system,
                permissions=sorted((PermissionCode(code) for code in codes), key=str),
            )
        )
    return result


def create_role(
    db: Session,
    *,
    code: str,
    name_ar: str,
    description: str,
    permissions: set[PermissionCode],
    actor: Principal,
    client: ClientContext,
) -> Role:
    if db.scalar(select(Role.id).where(Role.code == code)) is not None:
        raise IdentityConflict("رمز الدور مستخدم بالفعل")
    role = Role(
        code=code,
        name_ar=name_ar.strip(),
        description=description.strip(),
        is_system=False,
    )
    db.add(role)
    db.flush()
    permission_values = [code.value for code in permissions]
    permission_rows = list(
        db.scalars(select(Permission).where(Permission.code.in_(permission_values)))
    )
    db.add_all(
        RolePermission(role_id=role.id, permission_id=permission.id)
        for permission in permission_rows
    )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="identity.role.create",
        entity_type="role",
        entity_id=str(role.id),
        outcome="success",
        client=client,
        after_state={"code": role.code, "permissions": sorted(permissions)},
    )
    return role


def update_role_permissions(
    db: Session,
    *,
    role_id: UUID,
    permissions: set[PermissionCode],
    actor: Principal,
    client: ClientContext,
) -> None:
    role = db.get(Role, role_id)
    if role is None:
        raise IdentityNotFound("الدور غير موجود")
    if role.is_system:
        raise ProtectedOperation("الأدوار الأساسية ثابتة؛ أنشئ دورًا مخصصًا بدلًا من تعديلها")
    before = sorted(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
    )
    permission_values = [code.value for code in permissions]
    rows = list(db.scalars(select(Permission).where(Permission.code.in_(permission_values))))
    db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
    db.add_all(RolePermission(role_id=role.id, permission_id=row.id) for row in rows)
    affected_users = list(db.scalars(select(UserRole.user_id).where(UserRole.role_id == role.id)))
    if affected_users:
        db.execute(
            update(User)
            .where(User.id.in_(affected_users))
            .values(version=User.version + 1)
        )
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id.in_(affected_users), AuthSession.revoked_at.is_(None))
            .values(revoked_at=utc_now())
        )
    add_audit(
        db,
        actor_user_id=actor.user.id,
        event_type="identity.role.permissions.update",
        entity_type="role",
        entity_id=str(role.id),
        outcome="success",
        client=client,
        before_state={"permissions": before},
        after_state={"permissions": sorted(permissions)},
    )
