from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.dependencies import (
    CurrentPrincipal,
    DatabaseSession,
    client_context,
    enforce_csrf,
    enforce_permission,
)
from app.modules.identity.models import AuditLog
from app.modules.identity.permissions import PermissionCode
from app.modules.identity.schemas import (
    AuditLogView,
    CreateRoleRequest,
    CreateUserRequest,
    RoleView,
    UpdateRolePermissionsRequest,
    UpdateUserRequest,
    UserView,
)
from app.modules.identity.service import (
    IdentityConflict,
    IdentityNotFound,
    ProtectedOperation,
    create_role,
    create_user,
    delete_user,
    list_roles,
    list_users,
    update_role_permissions,
    update_user,
    user_view,
)

router = APIRouter(prefix="/identity")


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, IdentityNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if isinstance(exc, IdentityConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(exc))
    if isinstance(exc, ProtectedOperation):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    return HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))


@router.get("/users", response_model=list[UserView])
def users(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> list[UserView]:
    enforce_permission(request, db, principal, PermissionCode.USERS_READ)
    return list_users(db)


@router.post("/users", response_model=UserView, status_code=status.HTTP_201_CREATED)
def add_user(
    payload: CreateUserRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> UserView:
    enforce_permission(request, db, principal, PermissionCode.USERS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        user = create_user(
            db,
            username=payload.username,
            display_name=payload.display_name,
            password=payload.password,
            role_codes=payload.role_codes,
            must_change_password=payload.must_change_password,
            actor=principal,
            client=client_context(request),
        )
    except (IdentityConflict, IdentityNotFound, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = user_view(db, user)
    db.commit()
    return view


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(
    user_id: UUID,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> None:
    enforce_permission(request, db, principal, PermissionCode.USERS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        delete_user(
            db,
            target_user_id=user_id,
            actor=principal,
            client=client_context(request),
        )
    except (IdentityNotFound, ProtectedOperation) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    db.commit()


@router.patch("/users/{user_id}", response_model=UserView)
def edit_user(
    user_id: UUID,
    payload: UpdateUserRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> UserView:
    enforce_permission(request, db, principal, PermissionCode.USERS_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        user = update_user(
            db,
            target_user_id=user_id,
            actor=principal,
            client=client_context(request),
            display_name=payload.display_name,
            is_active=payload.is_active,
            role_codes=payload.role_codes,
            new_password=payload.new_password,
            must_change_password=payload.must_change_password,
        )
    except (IdentityNotFound, ProtectedOperation, ValueError) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    view = user_view(db, user)
    db.commit()
    return view


@router.get("/roles", response_model=list[RoleView])
def roles(request: Request, principal: CurrentPrincipal, db: DatabaseSession) -> list[RoleView]:
    enforce_permission(request, db, principal, PermissionCode.ROLES_READ)
    return list_roles(db)


@router.post("/roles", response_model=RoleView, status_code=status.HTTP_201_CREATED)
def add_role(
    payload: CreateRoleRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> RoleView:
    enforce_permission(request, db, principal, PermissionCode.ROLES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        role = create_role(
            db,
            code=payload.code,
            name_ar=payload.name_ar,
            description=payload.description,
            permissions=payload.permissions,
            actor=principal,
            client=client_context(request),
        )
    except IdentityConflict as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    db.flush()
    view = next(item for item in list_roles(db) if item.id == role.id)
    db.commit()
    return view


@router.put("/roles/{role_id}/permissions", response_model=RoleView)
def edit_role_permissions(
    role_id: UUID,
    payload: UpdateRolePermissionsRequest,
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
) -> RoleView:
    enforce_permission(request, db, principal, PermissionCode.ROLES_MANAGE)
    enforce_csrf(request, db, principal)
    try:
        update_role_permissions(
            db,
            role_id=role_id,
            permissions=payload.permissions,
            actor=principal,
            client=client_context(request),
        )
    except (IdentityNotFound, ProtectedOperation) as exc:
        db.rollback()
        raise _translate_error(exc) from exc
    db.flush()
    view = next(item for item in list_roles(db) if item.id == role_id)
    db.commit()
    return view


@router.get("/audit", response_model=list[AuditLogView])
def audit_log(
    request: Request,
    principal: CurrentPrincipal,
    db: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> list[AuditLogView]:
    enforce_permission(request, db, principal, PermissionCode.AUDIT_READ)
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(limit))
    return [
        AuditLogView(
            id=row.id,
            actor_user_id=row.actor_user_id,
            event_type=row.event_type,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            outcome=row.outcome,
            details=row.details,
            created_at=row.created_at,
        )
        for row in rows
    ]
