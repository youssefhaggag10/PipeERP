import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";
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
  LogOut,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { BrandMark } from "./BrandMark";

const navigation = [
  { label: "لوحة التشغيل", icon: Gauge, to: "/" },
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
  const { user, logout } = useAuth();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar__head">
          <BrandMark inverse />
        </div>
        <nav className="sidebar__nav" aria-label="التنقل الرئيسي">
          <p className="sidebar__eyebrow">مساحة العمل</p>
          {navigation.map(({ label, icon: Icon, to }) => to ? (
            <NavLink className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`} key={label} to={to} end>
              <Icon size={19} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ) : <button className="nav-item" key={label} disabled><Icon size={19} strokeWidth={1.8} /><span>{label}</span></button>)}
          {user?.permissions.includes("users.read") ? <NavLink className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`} to="/identity"><UsersRound size={19} /><span>المستخدمون والصلاحيات</span></NavLink> : null}
        </nav>
        <div className="sidebar__foot">
          <button className="nav-item" disabled>
            <Settings size={19} strokeWidth={1.8} />
            <span>الإعدادات</span>
          </button>
          <button className="nav-item" onClick={() => void logout()}>
            <LogOut size={19} strokeWidth={1.8} />
            <span>تسجيل الخروج</span>
          </button>
          <div className="profile-chip">
            <span className="profile-chip__avatar">{user?.display_name.charAt(0) ?? "م"}</span>
            <span>
              <strong>{user?.display_name ?? "مستخدم"}</strong>
              <small>{user?.roles.includes("system_admin") ? "الإدارة الكاملة" : "مستخدم النظام"}</small>
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
