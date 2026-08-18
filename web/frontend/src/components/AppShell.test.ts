import { describe, expect, it } from "vitest";

import { visibleNavigationItems } from "./navigation";

describe("permission-aware navigation", () => {
  it("shows only the dashboard and modules explicitly granted to a role", () => {
    const labels = visibleNavigationItems(["sales.read"]).map((item) => item.label);

    expect(labels).toEqual(["لوحة التشغيل", "المبيعات"]);
  });

  it("does not infer manage access from a read permission for another module", () => {
    const labels = visibleNavigationItems(["inventory.manage"]).map((item) => item.label);

    expect(labels).toEqual(["لوحة التشغيل"]);
  });

  it("exposes the purchasing workspace only to purchasing readers", () => {
    const items = visibleNavigationItems(["purchases.read"]);

    expect(items.map((item) => item.label)).toEqual(["لوحة التشغيل", "المشتريات"]);
    expect(items[1]?.to).toBe("/purchases");
  });
});
