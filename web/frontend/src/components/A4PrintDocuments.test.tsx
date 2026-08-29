import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import {
  BrandedDocumentPreview,
  BrandedStatementPreview,
  type PrintDocument,
  type Statement,
} from "./A4PrintDocuments";

const company = {
  name_ar: "ثري إيه بايب - 3A FOR PLASTIC PRODUCTS",
  phone: "01000000000",
  address: "المنوفية",
  tax_number: "",
  currency_code: "EGP",
};

const document: PrintDocument = {
  document_type: "weight_invoice",
  document_title: "فاتورة مبيعات بالوزن / الكارتة",
  document_number: "SI-1",
  document_date: "2026-08-20T10:30:00Z",
  order_number: "SO-1",
  partner_name_ar: "عميل",
  partner_code: "CUS-1",
  partner_phone: "0100",
  partner_address: "القاهرة",
  payment_methods: ["نقدي"],
  subtotal: "100",
  discount_amount: "0",
  transport_amount: "0",
  tax_amount: "0",
  original_total: "100",
  returned_total: "0",
  net_total: "100",
  paid: "40",
  refunded: "0",
  remaining: "60",
  notes: "",
  valid_until: null,
  card_number: "CARD-1",
  vehicle_number: "س ب ج 123",
  gross_weight_kg: "120",
  tare_weight_kg: "20",
  net_weight_kg: "100",
  lines: [{ code: "P-1", name: "ماسورة", quantity: "2", unit: "ماسورة", unit_price: "50", line_total: "100", notes: "", actual_weight_kg: "100", price_per_kg: "1" }],
  company,
};

describe("A4 print documents", () => {
  it("renders the Desktop weight-card columns and financial bands", () => {
    const markup = renderToStaticMarkup(<BrandedDocumentPreview document={document} />);
    expect(markup).toContain("فاتورة مبيعات بالوزن / الكارتة");
    expect(markup).toContain("رقم الكارتة");
    expect(markup).toContain("وزن الكارتة");
    expect(markup).toContain("إجمالي المتبقي");
    expect(markup).not.toContain("حراري");
  });

  it("always appends the Desktop statement summary page", () => {
    const statement: Statement = {
      company,
      partner_phone: "0100",
      detailed: false,
      include_drafts: false,
      invoice_details: {},
      statement: { partner_code: "CUS-1", partner_name_ar: "عميل", date_from: "2026-08-01", date_to: "2026-08-31", opening_balance: "0", closing_balance: "60", lines: [] },
      summary: { opening_balance: "0", standard_sales_total: "100", weight_sales_total: "0", returns_total: "0", receipts_total: "40", customer_refunds_total: "0", adjustments_total: "0", net_movement: "60", closing_balance: "60" },
    };
    const markup = renderToStaticMarkup(<BrandedStatementPreview data={statement} />);
    expect(markup).toContain("كشف حساب عميل");
    expect(markup).toContain("ملخص كشف حساب العميل");
    expect(markup).toContain("فواتير المبيعات العادية");
  });
});
