import {
  BarChart3,
  Boxes,
  CircleDollarSign,
  Factory,
  Gauge,
  Package,
  PackageCheck,
  Scale,
  ShoppingCart,
  ContactRound,
  type LucideIcon,
} from "lucide-react";

import type { Permission } from "../auth/permissions";

export type NavigationItem = {
  label: string;
  icon: LucideIcon;
  to?: string;
  permission?: Permission;
  children?: NavigationItem[];
};

const navigation: NavigationItem[] = [
  { label: "الرئيسية", icon: Gauge, to: "/" },
  {
    label: "CRM متابعة العملاء",
    icon: ContactRound,
    to: "/crm",
    permission: "crm.read",
  },
  {
    label: "الأصناف",
    icon: Package,
    to: "/products",
    permission: "products.read",
  },
  {
    label: "الموردين",
    icon: PackageCheck,
    to: "/partners?type=supplier",
    permission: "partners.read",
  },
  {
    label: "العملاء",
    icon: ContactRound,
    to: "/partners?type=customer",
    permission: "partners.read",
  },
  {
    label: "إعداد المخزن",
    icon: Boxes,
    to: "/warehouse",
    permission: "warehouses.read",
  },
  {
    label: "رصيد المخزون",
    icon: Boxes,
    to: "/inventory",
    permission: "inventory.read",
  },
  {
    label: "أرصدة الدفعات",
    icon: Package,
    to: "/inventory?view=lots",
    permission: "inventory.read",
  },
  {
    label: "المشتريات",
    icon: PackageCheck,
    to: "/purchases",
    permission: "purchases.read",
  },
  {
    label: "المبيعات",
    icon: ShoppingCart,
    to: "/sales",
    permission: "sales.read",
    children: [
      {
        label: "البيع بالوزن / الكارتة",
        icon: Scale,
        to: "/weight-sales",
        permission: "weight_sales.read",
      },
    ],
  },
  {
    label: "الحسابات",
    icon: CircleDollarSign,
    to: "/accounts",
    permission: "accounts.read",
  },
  {
    label: "كارت الصنف",
    icon: Package,
    to: "/inventory?view=stock-card",
    permission: "inventory.read",
  },
  {
    label: "التصنيع",
    icon: Factory,
    to: "/manufacturing",
    permission: "manufacturing.read",
  },
  {
    label: "التقارير",
    icon: BarChart3,
    to: "/reports",
    permission: "reports.read",
  },
];

export function visibleNavigationItems(
  permissions: readonly Permission[],
): NavigationItem[] {
  return navigation.flatMap((item) => {
    if (item.permission === undefined || permissions.includes(item.permission))
      return [item];
    const allowedChild = item.children?.find(
      (child) =>
        child.permission === undefined ||
        permissions.includes(child.permission),
    );
    return allowedChild
      ? [
          {
            ...item,
            to: allowedChild.to,
            permission: allowedChild.permission,
            children: undefined,
          },
        ]
      : [];
  });
}
