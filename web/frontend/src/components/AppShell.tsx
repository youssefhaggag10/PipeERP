import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  ChevronLeft,
  Menu,
  Search,
  Settings,
  UsersRound,
  LogOut,
  X,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { BrandMark } from "./BrandMark";
import { visibleNavigationItems } from "./navigation";

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const visibleNavigation = visibleNavigationItems(user?.permissions ?? []);
  const today = new Intl.DateTimeFormat("ar-EG", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());

  useEffect(() => {
    setMobileNavigationOpen(false);
  }, [location.pathname]);

  return (
    <div className="app-shell">
      <aside className={`sidebar ${mobileNavigationOpen ? "sidebar--open" : ""}`}>
        <div className="sidebar__head">
          <BrandMark inverse />
          <button
            className="sidebar__close"
            type="button"
            aria-label="إغلاق القائمة"
            onClick={() => setMobileNavigationOpen(false)}
          >
            <X size={20} />
          </button>
        </div>
        <nav className="sidebar__nav" aria-label="التنقل الرئيسي">
          <p className="sidebar__eyebrow">مساحة العمل</p>
          {visibleNavigation.map(({ label, icon: Icon, to }) => to ? (
            <NavLink className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`} key={label} to={to} end>
              <Icon size={19} strokeWidth={1.8} />
              <span>{label}</span>
            </NavLink>
          ) : <button className="nav-item" key={label} disabled><Icon size={19} strokeWidth={1.8} /><span>{label}</span></button>)}
          {user?.permissions.includes("users.read") ? <NavLink className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`} to="/identity"><UsersRound size={19} /><span>المستخدمون والصلاحيات</span></NavLink> : null}
        </nav>
        <div className="sidebar__foot">
          {user?.permissions.includes("settings.read") ? <NavLink className={({ isActive }) => `nav-item ${isActive ? "nav-item--active" : ""}`} to="/settings">
              <Settings size={19} strokeWidth={1.8} />
              <span>الإعدادات</span>
            </NavLink> : null}
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
      {mobileNavigationOpen ? (
        <button
          className="sidebar-backdrop"
          type="button"
          aria-label="إغلاق القائمة الجانبية"
          onClick={() => setMobileNavigationOpen(false)}
        />
      ) : null}

      <main className="main-panel">
        <header className="topbar">
          <div className="topbar__welcome">
            <button
              className="mobile-nav-button"
              type="button"
              aria-label="فتح القائمة الرئيسية"
              aria-expanded={mobileNavigationOpen}
              onClick={() => setMobileNavigationOpen(true)}
            >
              <Menu size={21} />
            </button>
            <div>
            <p className="topbar__date">{today}</p>
            <h1>صباح الخير</h1>
            </div>
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
