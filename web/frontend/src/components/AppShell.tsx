import {
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronDown,
  ChevronLeft,
  Menu,
  Settings,
  LogOut,
  X,
} from "lucide-react";

import { useAuth } from "../auth/AuthContext";
import { BrandMark } from "./BrandMark";
import { visibleNavigationItems } from "./navigation";

type HeaderLogoSettings = { image: string };
function readHeaderLogo(): HeaderLogoSettings {
  try {
    const value = JSON.parse(
      localStorage.getItem("pipeerp.header-logo")
        ?? localStorage.getItem("pipeerp.watermark")
        ?? "null",
    ) as Partial<HeaderLogoSettings> | null;
    return { image: value?.image ?? "" };
  } catch {
    return { image: "" };
  }
}

export function AppShell({ children }: { children: ReactNode }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [headerLogo, setHeaderLogo] = useState(readHeaderLogo);
  const [salesMenuOpen, setSalesMenuOpen] = useState(
    location.pathname === "/weight-sales",
  );
  const visibleNavigation = visibleNavigationItems(user?.permissions ?? []);

  useEffect(() => {
    setMobileNavigationOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    const update = () => setHeaderLogo(readHeaderLogo());
    window.addEventListener("pipeerp-header-logo-change", update);
    window.addEventListener("storage", update);
    return () => {
      window.removeEventListener("pipeerp-header-logo-change", update);
      window.removeEventListener("storage", update);
    };
  }, []);

  function itemIsActive(to: string) {
    const [pathname, search] = to.split("?");
    if (location.pathname !== pathname) return false;
    return search ? location.search === `?${search}` : location.search === "";
  }

  return (
    <div className="app-shell">
      <aside
        className={`sidebar ${mobileNavigationOpen ? "sidebar--open" : ""}`}
      >
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
          {visibleNavigation.map(({ label, icon: Icon, to, children }) => {
            if (!to)
              return (
                <button className="nav-item" key={label} disabled>
                  <Icon size={19} strokeWidth={1.8} />
                  <span>{label}</span>
                </button>
              );
            if (!children?.length)
              return (
                <Link
                  className={`nav-item ${itemIsActive(to) ? "nav-item--active" : ""}`}
                  key={label}
                  to={to}
                >
                  <Icon size={19} strokeWidth={1.8} />
                  <span>{label}</span>
                </Link>
              );
            const visibleChildren = children.filter(
              (child) =>
                !child.permission ||
                user?.permissions.includes(child.permission),
            );
            return (
              <div className="nav-group" key={label}>
                <div className="nav-group__row">
                  <Link
                    className={`nav-item ${itemIsActive(to) || visibleChildren.some((child) => child.to && itemIsActive(child.to)) ? "nav-item--active" : ""}`}
                    to={to}
                  >
                    <Icon size={19} strokeWidth={1.8} />
                    <span>{label}</span>
                  </Link>
                  {visibleChildren.length ? (
                    <button
                      type="button"
                      className="nav-group__toggle"
                      aria-label="قائمة المبيعات"
                      aria-expanded={salesMenuOpen}
                      onClick={() => setSalesMenuOpen((open) => !open)}
                    >
                      <ChevronDown size={16} />
                    </button>
                  ) : null}
                </div>
                {salesMenuOpen ? (
                  <div className="nav-group__children">
                    {visibleChildren.map((child) => {
                      const ChildIcon = child.icon;
                      return (
                        <Link
                          className={`nav-item nav-item--child ${child.to && itemIsActive(child.to) ? "nav-item--active" : ""}`}
                          key={child.label}
                          to={child.to!}
                        >
                          <ChildIcon size={17} />
                          <span>{child.label}</span>
                        </Link>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </nav>
        <div className="sidebar__foot">
          {user?.permissions.includes("settings.read") ? (
            <NavLink
              className={({ isActive }) =>
                `nav-item ${isActive ? "nav-item--active" : ""}`
              }
              to="/settings"
            >
              <Settings size={19} strokeWidth={1.8} />
              <span>الإعدادات</span>
            </NavLink>
          ) : null}
          <button className="nav-item" onClick={() => void logout()}>
            <LogOut size={19} strokeWidth={1.8} />
            <span>تسجيل الخروج</span>
          </button>
          <div className="profile-chip">
            <span className="profile-chip__avatar">
              {user?.display_name.charAt(0) ?? "م"}
            </span>
            <span>
              <strong>{user?.display_name ?? "مستخدم"}</strong>
              <small>
                {user?.roles.includes("system_admin")
                  ? "الإدارة الكاملة"
                  : "مستخدم النظام"}
              </small>
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
            <span className="topbar__company-logo">
              {headerLogo.image ? (
                <img src={headerLogo.image} alt="شعار 3A PIPE" />
              ) : (
                <BrandMark compact />
              )}
            </span>
            <h1>3A PIPE — {user?.display_name ?? "مستخدم"}</h1>
          </div>
          <div className="topbar__actions">
            <button
              className="icon-button"
              aria-label="مركز أنشطة العملاء"
              title={
                user?.permissions.includes("crm.read")
                  ? "فتح مركز أنشطة العملاء"
                  : "لا توجد صلاحية لمركز الأنشطة"
              }
              disabled={!user?.permissions.includes("crm.read")}
              onClick={() => navigate("/crm?tab=activities")}
            >
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
