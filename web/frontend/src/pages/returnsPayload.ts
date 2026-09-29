export type ReturnLineMode = "full_remaining" | "selected_sources";

export type ReturnSource = {
  source_id: string;
  source_kind: "sales_delivery_allocation" | "purchase_receipt_layer";
  lot_number: string;
  source_reference: string;
  source_date: string;
  warehouse_name_ar: string;
  stable_label: string;
  original_quantity: string;
  already_returned_quantity: string;
  remaining_returnable_quantity: string;
  original_weight_kg: string;
  already_returned_weight_kg: string;
  remaining_returnable_weight_kg: string;
};

export type ReturnLine = {
  source_line_id: string;
  product_code: string;
  product_name_ar: string;
  unit: string;
  cost_basis: "quantity" | "weight";
  remaining_quantity: string;
  remaining_weight_kg: string;
  sources: ReturnSource[];
};

type ReturnLinePayload = {
  source_line_id: string;
  mode: ReturnLineMode;
  sources?: Array<{
    source_id: string;
    quantity: string;
    weight_kg: string;
  }>;
};

export function buildReturnLinePayloads(
  lines: ReturnLine[],
  lineModes: Record<string, ReturnLineMode | undefined>,
  sourceAmounts: Record<string, string>,
): ReturnLinePayload[] {
  return lines.flatMap<ReturnLinePayload>((line): ReturnLinePayload[] => {
    const mode = lineModes[line.source_line_id];
    if (mode === "full_remaining")
      return [{ source_line_id: line.source_line_id, mode }];
    if (mode !== "selected_sources") return [];
    const sources = line.sources.flatMap((source) => {
      const amount = sourceAmounts[source.source_id] || "0";
      if (Number(amount) <= 0) return [];
      return [
        {
          source_id: source.source_id,
          quantity: line.cost_basis === "quantity" ? amount : "0",
          weight_kg: line.cost_basis === "weight" ? amount : "0",
        },
      ];
    });
    return sources.length
      ? [{ source_line_id: line.source_line_id, mode, sources }]
      : [];
  });
}

export function sourceOperationalSummary(
  line: ReturnLine,
  source: ReturnSource,
): string {
  const original =
    line.cost_basis === "weight"
      ? source.original_weight_kg
      : source.original_quantity;
  const returned =
    line.cost_basis === "weight"
      ? source.already_returned_weight_kg
      : source.already_returned_quantity;
  const remaining =
    line.cost_basis === "weight"
      ? source.remaining_returnable_weight_kg
      : source.remaining_returnable_quantity;
  const unit = line.cost_basis === "weight" ? "كجم" : line.unit;
  return `الأصل ${original} ${unit} · مرتجع سابقًا ${returned} ${unit} · متاح ${remaining} ${unit}`;
}
