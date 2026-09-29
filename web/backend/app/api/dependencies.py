from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.infrastructure.database.session import get_database_session
from app.modules.identity.permissions import PermissionCode
from app.modules.identity.service import (
    ClientContext,
    Principal,
    add_audit,
    principal_from_access_token,
    validate_csrf,
)

ACCESS_COOKIE = "pipeerp_access"
REFRESH_COOKIE = "pipeerp_refresh"
CSRF_COOKIE = "pipeerp_csrf"

DatabaseSession = Annotated[Session, Depends(get_database_session)]


def client_context(request: Request) -> ClientContext:
    return ClientContext(
        ip_address=request.client.host[:64] if request.client is not None else None,
        user_agent=request.headers.get("user-agent", "")[:512] or None,
        request_id=getattr(request.state, "request_id", None),
    )


def current_principal(request: Request, db: DatabaseSession) -> Principal:
    token = request.cookies.get(ACCESS_COOKIE)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "يجب تسجيل الدخول")
    principal = principal_from_access_token(
        db,
        token=token,
        secret_key=get_settings().secret_key,
    )
    if principal is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "انتهت الجلسة أو تم إبطالها")
    allowed_while_password_change = {
        "/api/v1/auth/me",
        "/api/v1/auth/change-password",
        "/api/v1/auth/logout",
    }
    must_change_password = principal.user.must_change_password
    if must_change_password and request.url.path not in allowed_while_password_change:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "يجب تغيير كلمة المرور المؤقتة أولًا",
        )
    return principal


CurrentPrincipal = Annotated[Principal, Depends(current_principal)]


def enforce_csrf(request: Request, db: Session, principal: Principal) -> None:
    if validate_csrf(
        principal,
        request.headers.get("x-csrf-token"),
        request.cookies.get(CSRF_COOKIE),
    ):
        return
    add_audit(
        db,
        actor_user_id=principal.user.id,
        event_type="security.csrf.denied",
        entity_type="request",
        outcome="denied",
        client=client_context(request),
    )
    db.commit()
    raise HTTPException(status.HTTP_403_FORBIDDEN, "رمز الحماية غير صالح")


def enforce_permission(
    request: Request,
    db: Session,
    principal: Principal,
    permission: PermissionCode,
) -> None:
    if permission in principal.permissions:
        return
    add_audit(
        db,
        actor_user_id=principal.user.id,
        event_type="security.permission.denied",
        entity_type="permission",
        entity_id=permission.value,
        outcome="denied",
        client=client_context(request),
    )
    db.commit()
    raise HTTPException(status.HTTP_403_FORBIDDEN, "ليست لديك صلاحية لتنفيذ هذه العملية")
