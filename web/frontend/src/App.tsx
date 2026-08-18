import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { DashboardPage } from "./pages/DashboardPage";
import { IdentityPage } from "./pages/IdentityPage";
import { LoginPage } from "./pages/LoginPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      <Route path="/identity" element={<ProtectedRoute><IdentityPage /></ProtectedRoute>} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
      {import.meta.env.DEV ? (
        <Route path="/design-preview" element={<DashboardPage />} />
      ) : null}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
