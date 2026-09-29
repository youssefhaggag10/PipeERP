import type { Permission } from "../auth/permissions";

export type DashboardAction = {
  label: string;
  description: string;
  to: string;
  readPermission: Permission;
  managePermission?: Permission;
};

export const dashboardActions: DashboardAction[] = [
  { label: "أمر بيع", description: "بالقطعة أو الوزن", to: "/sales?focus=new", readPermission: "sales.read", managePermission: "sales.manage" },
  { label: "استلام مشتريات", description: "افتح أمرًا معتمدًا وسجّل الاستلام", to: "/purchases?focus=receipt", readPermission: "purchases.read", managePermission: "purchases.manage" },
  { label: "أمر تصنيع", description: "تخطيط خلطة جديدة", to: "/manufacturing?focus=new", readPermission: "manufacturing.read", managePermission: "manufacturing.manage" },
  { label: "كارت صنف", description: "تتبّع الحركة والرصيد", to: "/inventory?view=stock-card", readPermission: "inventory.read" },
];

export function visibleDashboardActions(permissions: readonly Permission[]) {
  return dashboardActions.filter((action) => permissions.includes(action.readPermission));
}

export function firstManageableAction(permissions: readonly Permission[]) {
  return visibleDashboardActions(permissions).find(
    (action) => !action.managePermission || permissions.includes(action.managePermission),
  );
}
