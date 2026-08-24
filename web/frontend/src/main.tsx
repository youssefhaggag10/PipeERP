import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import { App } from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { AppErrorBoundary } from "./components/AppErrorBoundary";
import "./styles.css";

try {
  const appearance = JSON.parse(localStorage.getItem("pipeerp.appearance") ?? "null") as {
    theme?: string;
    fontSize?: number;
    scale?: number;
  } | null;
  if (appearance) {
    document.documentElement.dataset.theme = appearance.theme ?? "system";
    document.documentElement.style.setProperty("--app-font-size", `${appearance.fontSize ?? 14}px`);
    document.documentElement.style.setProperty("--app-scale", String((appearance.scale ?? 100) / 100));
  }
} catch {
  localStorage.removeItem("pipeerp.appearance");
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <AppErrorBoundary>
        <AuthProvider>
          <App />
        </AuthProvider>
      </AppErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
);
