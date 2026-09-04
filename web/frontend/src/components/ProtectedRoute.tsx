import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { hasEveryPermission, type Permission } from "../auth/permissions";

type ProtectedRouteProps = {
  children: ReactNode;
  requiredPermissions?: readonly Permission[];
};

export function ProtectedRoute({ children, requiredPermissions = [] }: ProtectedRouteProps) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <main className="route-loading">جارٍ تجهيز مساحة العمل…</main>;
  if (!user) return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  if (!hasEveryPermission(user.permissions, requiredPermissions)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
