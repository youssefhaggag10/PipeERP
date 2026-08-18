import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IdentityPage } from "./pages/IdentityPage";
import { LoginPage } from "./pages/LoginPage";
import { PartnersPage } from "./pages/PartnersPage";
import { ProductsPage } from "./pages/ProductsPage";
import { SettingsPage } from "./pages/SettingsPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      <Route path="/identity" element={<ProtectedRoute requiredPermissions={["users.read", "roles.read"]}><IdentityPage /></ProtectedRoute>} />
      <Route path="/products" element={<ProtectedRoute requiredPermissions={["products.read"]}><ProductsPage /></ProtectedRoute>} />
      <Route path="/partners" element={<ProtectedRoute requiredPermissions={["partners.read"]}><PartnersPage /></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute requiredPermissions={["settings.read"]}><SettingsPage /></ProtectedRoute>} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
      {import.meta.env.DEV ? (
        <Route path="/design-preview" element={<DashboardPage />} />
      ) : null}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
