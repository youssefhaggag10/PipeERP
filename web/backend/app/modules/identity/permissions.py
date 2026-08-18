from enum import StrEnum


class PermissionCode(StrEnum):
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    ROLES_READ = "roles.read"
    ROLES_MANAGE = "roles.manage"
    AUDIT_READ = "audit.read"


SYSTEM_ROLES: dict[str, tuple[str, set[PermissionCode]]] = {
    "system_admin": (
        "مدير النظام",
        set(PermissionCode),
    ),
    "operations_manager": (
        "المدير التشغيلي",
        {PermissionCode.USERS_READ, PermissionCode.ROLES_READ, PermissionCode.AUDIT_READ},
    ),
}
