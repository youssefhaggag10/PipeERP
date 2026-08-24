import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "./AppShell";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: {
      display_name: "مدير النظام",
      permissions: [],
      roles: ["system_admin"],
    },
    logout: vi.fn(),
  }),
}));

describe("fixed header company logo", () => {
  it("renders the logo beside the user name and no page watermark", () => {
    const markup = renderToStaticMarkup(
      <MemoryRouter>
        <AppShell><div>المحتوى</div></AppShell>
      </MemoryRouter>,
    );

    expect(markup).toContain("3A PIPE — مدير النظام");
    expect(markup).toContain("topbar__company-logo");
    expect(markup.indexOf("topbar__company-logo")).toBeLessThan(
      markup.indexOf("3A PIPE — مدير النظام"),
    );
    expect(markup).not.toContain("app-watermark");
  });
});
