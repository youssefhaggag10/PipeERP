import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { DashboardPage } from "./DashboardPage";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      permissions: [
        "sales.read",
        "sales.manage",
        "purchases.read",
        "purchases.manage",
        "manufacturing.read",
        "manufacturing.manage",
        "inventory.read",
      ],
    },
  }),
}));

vi.mock("../components/AppShell", () => ({
  AppShell: ({ children }: { children: React.ReactNode }) => children,
}));

vi.mock("../lib/api", () => ({
  api: vi.fn(),
}));

describe("enhanced dashboard owner-approved exception", () => {
  it("keeps daily metrics, operating activity, alerts and quick actions", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    );

    for (const label of [
      "مبيعات اليوم",
      "أوامر تحت التشغيل",
      "تنبيهات المخزون",
      "وزن مباع اليوم",
      "حركة التشغيل",
      "يحتاج انتباهك",
      "إجراءات سريعة",
    ]) {
      expect(markup).toContain(label);
    }
  });
});
