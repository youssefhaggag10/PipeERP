import { describe, expect, it } from "vitest";

import {
  buildReturnLinePayloads,
  sourceOperationalSummary,
} from "./returnsPayload";

const line = {
  source_line_id: "line-1",
  product_code: "P-1",
  product_name_ar: "صنف متعدد المصادر",
  unit: "وحدة",
  cost_basis: "quantity" as const,
  remaining_quantity: "20",
  remaining_weight_kg: "0",
  sources: [
    {
      source_id: "source-a",
      source_kind: "sales_delivery_allocation" as const,
      lot_number: "LOT-A",
      source_reference: "SD-1",
      source_date: "2026-09-01T10:00:00Z",
      warehouse_name_ar: "المصنع",
      stable_label: "مصدر التسليم 1",
      original_quantity: "5",
      already_returned_quantity: "1",
      remaining_returnable_quantity: "4",
      original_weight_kg: "0",
      already_returned_weight_kg: "0",
      remaining_returnable_weight_kg: "0",
    },
    {
      source_id: "source-b",
      source_kind: "sales_delivery_allocation" as const,
      lot_number: "",
      source_reference: "SD-1",
      source_date: "2026-09-01T10:00:00Z",
      warehouse_name_ar: "المصنع",
      stable_label: "مصدر التسليم 2",
      original_quantity: "15",
      already_returned_quantity: "0",
      remaining_returnable_quantity: "15",
      original_weight_kg: "0",
      already_returned_weight_kg: "0",
      remaining_returnable_weight_kg: "0",
    },
  ],
};

describe("returns source selection", () => {
  it("sends full_remaining without forcing manual source selection", () => {
    expect(
      buildReturnLinePayloads([line], { "line-1": "full_remaining" }, {}),
    ).toEqual([{ source_line_id: "line-1", mode: "full_remaining" }]);
  });

  it("sends only explicitly selected partial sources", () => {
    expect(
      buildReturnLinePayloads(
        [line],
        { "line-1": "selected_sources" },
        { "source-a": "2", "source-b": "0" },
      ),
    ).toEqual([
      {
        source_line_id: "line-1",
        mode: "selected_sources",
        sources: [{ source_id: "source-a", quantity: "2", weight_kg: "0" }],
      },
    ]);
  });

  it("shows operational provenance without exposing inventory cost", () => {
    const summary = sourceOperationalSummary(line, line.sources[0]!);
    expect(summary).toContain("الأصل 5 وحدة");
    expect(summary).toContain("مرتجع سابقًا 1 وحدة");
    expect(summary).toContain("متاح 4 وحدة");
    expect(summary).not.toContain("تكلفة");
    expect(summary).not.toContain("سعر");
  });
});
