import { Navigate, Route, Routes } from "react-router-dom";

import { DashboardPage } from "./pages/DashboardPage";
import { LoginPage } from "./pages/LoginPage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      {import.meta.env.DEV ? (
        <Route path="/design-preview" element={<DashboardPage />} />
      ) : null}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
