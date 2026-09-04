import { describe, expect, it } from "vitest";

import { visibleNavigationItems } from "./navigation";

describe("permission-aware navigation", () => {
  it("shows only the dashboard and modules explicitly granted to a role", () => {
    const labels = visibleNavigationItems(["sales.read"]).map((item) => item.label);

    expect(labels).toEqual(["الرئيسية", "المبيعات"]);
  });

  it("does not infer manage access from a read permission for another module", () => {
    const labels = visibleNavigationItems(["inventory.manage"]).map((item) => item.label);

    expect(labels).toEqual(["الرئيسية"]);
  });

  it("exposes the purchasing workspace only to purchasing readers", () => {
    const items = visibleNavigationItems(["purchases.read"]);

    expect(items.map((item) => item.label)).toEqual(["الرئيسية", "المشتريات"]);
    expect(items[1]?.to).toBe("/purchases");
  });

  it("keeps piece and weight sales navigation permissions independent", () => {
    const piece = visibleNavigationItems(["sales.read"]);
    const weight = visibleNavigationItems(["weight_sales.read"]);

    expect(piece.map((item) => item.to)).toEqual(["/", "/sales"]);
    expect(weight.map((item) => item.to)).toEqual(["/", "/weight-sales"]);
  });

  it("links authorized accountants to the treasury workspace", () => {
    const items = visibleNavigationItems(["accounts.read"]);
    expect(items.find((item) => item.label === "الحسابات")?.to).toBe("/accounts");
  });

  it("links manufacturing readers to the responsive manufacturing workspace", () => {
    const items = visibleNavigationItems(["manufacturing.read"]);

    expect(items.map((item) => item.label)).toEqual(["الرئيسية", "التصنيع"]);
    expect(items[1]?.to).toBe("/manufacturing");
  });

  it("does not expose a standalone returns module because desktop handles returns in accounts", () => {
    const items = visibleNavigationItems(["returns.read"]);

    expect(items.map((item) => item.label)).toEqual(["الرئيسية"]);
  });

  it("links report readers to the reports and A4 workspace", () => {
    const items = visibleNavigationItems(["reports.read"]);

    expect(items.map((item) => item.label)).toEqual(["الرئيسية", "التقارير"]);
    expect(items[1]?.to).toBe("/reports");
  });
});
