import { Navigate, Route, Routes } from "react-router-dom";

import { ProtectedRoute } from "./components/ProtectedRoute";
import { ChangePasswordPage } from "./pages/ChangePasswordPage";
import { CrmPage } from "./pages/CrmPage";
import { DashboardPage } from "./pages/DashboardPage";
import { InventoryPage } from "./pages/InventoryPage";
import { LoginPage } from "./pages/LoginPage";
import { ManufacturingPage } from "./pages/ManufacturingPage";
import { PartnersPage } from "./pages/PartnersPage";
import { ProductsPage } from "./pages/ProductsPage";
import { PrintDesignPreviewPage } from "./pages/PrintDesignPreviewPage";
import { PurchasesPage } from "./pages/PurchasesPage";
import { ReportsPage } from "./pages/ReportsPage";
import { SalesPage } from "./pages/SalesPage";
import { SettingsPage } from "./pages/SettingsPage";
import { TreasuryPage } from "./pages/TreasuryPage";
import { WarehousePage } from "./pages/WarehousePage";

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
      <Route path="/crm" element={<ProtectedRoute requiredPermissions={["crm.read"]}><CrmPage /></ProtectedRoute>} />
      <Route path="/products" element={<ProtectedRoute requiredPermissions={["products.read"]}><ProductsPage /></ProtectedRoute>} />
      <Route path="/partners" element={<ProtectedRoute requiredPermissions={["partners.read"]}><PartnersPage /></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute requiredPermissions={["settings.read"]}><SettingsPage /></ProtectedRoute>} />
      <Route path="/warehouse" element={<ProtectedRoute requiredPermissions={["warehouses.read"]}><WarehousePage /></ProtectedRoute>} />
      <Route path="/inventory" element={<ProtectedRoute requiredPermissions={["inventory.read"]}><InventoryPage /></ProtectedRoute>} />
      <Route path="/manufacturing" element={<ProtectedRoute requiredPermissions={["manufacturing.read"]}><ManufacturingPage /></ProtectedRoute>} />
      <Route path="/purchases" element={<ProtectedRoute requiredPermissions={["purchases.read"]}><PurchasesPage /></ProtectedRoute>} />
      <Route path="/sales" element={<ProtectedRoute requiredPermissions={["sales.read"]}><SalesPage /></ProtectedRoute>} />
      <Route path="/weight-sales" element={<ProtectedRoute requiredPermissions={["weight_sales.read"]}><SalesPage /></ProtectedRoute>} />
      <Route path="/accounts" element={<ProtectedRoute requiredPermissions={["accounts.read"]}><TreasuryPage /></ProtectedRoute>} />
      <Route path="/reports" element={<ProtectedRoute requiredPermissions={["reports.read"]}><ReportsPage /></ProtectedRoute>} />
      <Route path="/change-password" element={<ProtectedRoute><ChangePasswordPage /></ProtectedRoute>} />
      {import.meta.env.DEV ? (
        <>
          <Route path="/design-preview" element={<DashboardPage />} />
          <Route path="/print-design-preview" element={<PrintDesignPreviewPage />} />
        </>
      ) : null}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
