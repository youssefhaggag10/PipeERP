from enum import StrEnum


class PermissionCode(StrEnum):
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    ROLES_READ = "roles.read"
    ROLES_MANAGE = "roles.manage"
    AUDIT_READ = "audit.read"
    PRODUCTS_READ = "products.read"
    PRODUCTS_MANAGE = "products.manage"
    PARTNERS_READ = "partners.read"
    PARTNERS_MANAGE = "partners.manage"
    WAREHOUSES_READ = "warehouses.read"
    WAREHOUSES_MANAGE = "warehouses.manage"
    INVENTORY_READ = "inventory.read"
    INVENTORY_MANAGE = "inventory.manage"
    PURCHASES_READ = "purchases.read"
    PURCHASES_MANAGE = "purchases.manage"
    SALES_READ = "sales.read"
    SALES_MANAGE = "sales.manage"
    WEIGHT_SALES_READ = "weight_sales.read"
    WEIGHT_SALES_MANAGE = "weight_sales.manage"
    MANUFACTURING_READ = "manufacturing.read"
    MANUFACTURING_MANAGE = "manufacturing.manage"
    ACCOUNTS_READ = "accounts.read"
    ACCOUNTS_MANAGE = "accounts.manage"
    RETURNS_READ = "returns.read"
    RETURNS_MANAGE = "returns.manage"
    REPORTS_READ = "reports.read"
    SETTINGS_READ = "settings.read"
    SETTINGS_MANAGE = "settings.manage"


PERMISSION_NAMES_AR: dict[PermissionCode, str] = {
    PermissionCode.USERS_READ: "عرض المستخدمين",
    PermissionCode.USERS_MANAGE: "إدارة المستخدمين",
    PermissionCode.ROLES_READ: "عرض الأدوار",
    PermissionCode.ROLES_MANAGE: "إدارة الأدوار",
    PermissionCode.AUDIT_READ: "عرض سجل التدقيق",
    PermissionCode.PRODUCTS_READ: "عرض المنتجات",
    PermissionCode.PRODUCTS_MANAGE: "إدارة المنتجات",
    PermissionCode.PARTNERS_READ: "عرض العملاء والموردين",
    PermissionCode.PARTNERS_MANAGE: "إدارة العملاء والموردين",
    PermissionCode.WAREHOUSES_READ: "عرض المخازن",
    PermissionCode.WAREHOUSES_MANAGE: "إدارة المخازن",
    PermissionCode.INVENTORY_READ: "عرض المخزون",
    PermissionCode.INVENTORY_MANAGE: "إدارة المخزون",
    PermissionCode.PURCHASES_READ: "عرض المشتريات",
    PermissionCode.PURCHASES_MANAGE: "إدارة المشتريات",
    PermissionCode.SALES_READ: "عرض المبيعات",
    PermissionCode.SALES_MANAGE: "إدارة المبيعات",
    PermissionCode.WEIGHT_SALES_READ: "عرض البيع بالوزن",
    PermissionCode.WEIGHT_SALES_MANAGE: "إدارة البيع بالوزن",
    PermissionCode.MANUFACTURING_READ: "عرض التصنيع",
    PermissionCode.MANUFACTURING_MANAGE: "إدارة التصنيع",
    PermissionCode.ACCOUNTS_READ: "عرض الحسابات",
    PermissionCode.ACCOUNTS_MANAGE: "إدارة الحسابات",
    PermissionCode.RETURNS_READ: "عرض المرتجعات",
    PermissionCode.RETURNS_MANAGE: "إدارة المرتجعات",
    PermissionCode.REPORTS_READ: "عرض التقارير",
    PermissionCode.SETTINGS_READ: "عرض الإعدادات",
    PermissionCode.SETTINGS_MANAGE: "إدارة الإعدادات",
}


OPERATIONS_READ_PERMISSIONS = {
    PermissionCode.PRODUCTS_READ,
    PermissionCode.PARTNERS_READ,
    PermissionCode.WAREHOUSES_READ,
    PermissionCode.INVENTORY_READ,
    PermissionCode.PURCHASES_READ,
    PermissionCode.SALES_READ,
    PermissionCode.WEIGHT_SALES_READ,
    PermissionCode.MANUFACTURING_READ,
    PermissionCode.ACCOUNTS_READ,
    PermissionCode.RETURNS_READ,
    PermissionCode.REPORTS_READ,
    PermissionCode.SETTINGS_READ,
}


SYSTEM_ROLES: dict[str, tuple[str, set[PermissionCode]]] = {
    "system_admin": (
        "مدير النظام",
        set(PermissionCode),
    ),
    "operations_manager": (
        "المدير التشغيلي",
        {
            PermissionCode.USERS_READ,
            PermissionCode.ROLES_READ,
            PermissionCode.AUDIT_READ,
            *OPERATIONS_READ_PERMISSIONS,
        },
    ),
}
