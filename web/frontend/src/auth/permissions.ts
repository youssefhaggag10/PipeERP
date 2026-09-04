export const permissionLabels = {
  "users.read": "عرض المستخدمين",
  "users.manage": "إدارة المستخدمين",
  "roles.read": "عرض الأدوار",
  "roles.manage": "إدارة الأدوار",
  "audit.read": "عرض سجل التدقيق",
  "crm.read": "عرض متابعة العملاء",
  "crm.manage": "إدارة متابعة العملاء",
  "products.read": "عرض المنتجات",
  "products.manage": "إدارة المنتجات",
  "partners.read": "عرض العملاء والموردين",
  "partners.manage": "إدارة العملاء والموردين",
  "warehouses.read": "عرض المخازن",
  "warehouses.manage": "إدارة المخازن",
  "inventory.read": "عرض المخزون",
  "inventory.manage": "إدارة المخزون",
  "purchases.read": "عرض المشتريات",
  "purchases.manage": "إدارة المشتريات",
  "sales.read": "عرض المبيعات",
  "sales.manage": "إدارة المبيعات",
  "weight_sales.read": "عرض البيع بالوزن",
  "weight_sales.manage": "إدارة البيع بالوزن",
  "manufacturing.read": "عرض التصنيع",
  "manufacturing.manage": "إدارة التصنيع",
  "accounts.read": "عرض الحسابات",
  "accounts.manage": "إدارة الحسابات",
  "returns.read": "عرض المرتجعات",
  "returns.manage": "إدارة المرتجعات",
  "reports.read": "عرض التقارير",
  "settings.read": "عرض الإعدادات",
  "settings.manage": "إدارة الإعدادات",
} as const;

export type Permission = keyof typeof permissionLabels;

export function hasEveryPermission(
  granted: readonly Permission[],
  required: readonly Permission[],
): boolean {
  return required.every((permission) => granted.includes(permission));
}
