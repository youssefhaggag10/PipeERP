import { describe, expect, it } from "vitest";

import { firstManageableAction, visibleDashboardActions } from "./dashboardActions";

describe("dashboard actions", () => {
  it("shows only actions the user can open", () => {
    expect(visibleDashboardActions(["purchases.read"]).map((item) => item.label)).toEqual([
      "استلام مشتريات",
    ]);
  });

  it("selects a genuinely manageable new operation", () => {
    const action = firstManageableAction([
      "sales.read",
      "purchases.read",
      "purchases.manage",
    ]);
    expect(action?.to).toBe("/purchases?focus=receipt");
  });

  it("allows read-only stock card navigation", () => {
    expect(firstManageableAction(["inventory.read"])?.to).toBe("/inventory?view=stock-card");
  });
});
