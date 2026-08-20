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
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import type { Permission } from "../auth/permissions";

export type NavigationItem = {
  label: string;
  icon: LucideIcon;
  to?: string;
  permission?: Permission;
};

const navigation: NavigationItem[] = [
  { label: "لوحة التشغيل", icon: Gauge, to: "/" },
  { label: "المنتجات", icon: Package, to: "/products", permission: "products.read" },
  { label: "المبيعات", icon: ShoppingCart, to: "/sales", permission: "sales.read" },
  { label: "البيع بالوزن", icon: Scale, to: "/weight-sales", permission: "weight_sales.read" },
  { label: "المشتريات", icon: PackageCheck, to: "/purchases", permission: "purchases.read" },
  { label: "المخزون", icon: Boxes, to: "/inventory", permission: "inventory.read" },
  { label: "التصنيع", icon: Factory, to: "/manufacturing", permission: "manufacturing.read" },
  { label: "الحسابات", icon: CircleDollarSign, to: "/accounts", permission: "accounts.read" },
  {
    label: "العملاء والموردون",
    icon: UsersRound,
    to: "/partners",
    permission: "partners.read",
  },
  { label: "التقارير", icon: BarChart3, permission: "reports.read" },
];

export function visibleNavigationItems(permissions: readonly Permission[]): NavigationItem[] {
  return navigation.filter(
    ({ permission }) => permission === undefined || permissions.includes(permission),
  );
}
