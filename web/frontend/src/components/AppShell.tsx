import type { ReactNode } from "react";
import {
  BarChart3,
  Boxes,
  ChevronLeft,
  CircleDollarSign,
  Factory,
  Gauge,
  PackageCheck,
  Scale,
  Search,
  Settings,
  ShoppingCart,
  UsersRound,
} from "lucide-react";

import { BrandMark } from "./BrandMark";

const navigation = [
  { label: "لوحة التشغيل", icon: Gauge, active: true },
  { label: "المبيعات", icon: ShoppingCart },
  { label: "البيع بالوزن", icon: Scale },
  { label: "المشتريات", icon: PackageCheck },
  { label: "المخزون", icon: Boxes },
  { label: "التصنيع", icon: Factory },
  { label: "الحسابات", icon: CircleDollarSign },
  { label: "العملاء والموردون", icon: UsersRound },
  { label: "التقارير", icon: BarChart3 },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__head">
          <BrandMark inverse />
        </div>
        <nav className="sidebar__nav" aria-label="التنقل الرئيسي">
          <p className="sidebar__eyebrow">مساحة العمل</p>
          {navigation.map(({ label, icon: Icon, active }) => (
            <button className={`nav-item ${active ? "nav-item--active" : ""}`} key={label}>
              <Icon size={19} strokeWidth={1.8} />
              <span>{label}</span>
              {active ? <span className="nav-item__marker" /> : null}
            </button>
          ))}
        </nav>
        <div className="sidebar__foot">
          <button className="nav-item">
            <Settings size={19} strokeWidth={1.8} />
            <span>الإعدادات</span>
          </button>
          <div className="profile-chip">
            <span className="profile-chip__avatar">م</span>
            <span>
              <strong>مدير النظام</strong>
              <small>الإدارة الكاملة</small>
            </span>
            <ChevronLeft size={17} />
          </div>
        </div>
      </aside>

      <main className="main-panel">
        <header className="topbar">
          <div>
            <p className="topbar__date">الثلاثاء، 18 أغسطس 2026</p>
            <h1>صباح الخير</h1>
          </div>
          <div className="topbar__actions">
            <label className="global-search">
              <Search size={18} />
              <input aria-label="البحث" placeholder="ابحث عن مستند أو منتج..." />
              <kbd>F2</kbd>
            </label>
            <button className="icon-button" aria-label="الإشعارات">
              <span className="notification-dot" />
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" />
              </svg>
            </button>
          </div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}
