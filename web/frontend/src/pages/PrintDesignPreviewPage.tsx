import {
  BrandedDocumentPreview,
  BrandedStatementPreview,
  type PrintDocument,
  type Statement,
} from "../components/A4PrintDocuments";

const preview: PrintDocument = {
  document_type: "sales_invoice",
  document_title: "فاتورة مبيعات",
  document_number: "SI00003",
  document_date: "2026-08-16T02:17:42+02:00",
  order_number: "SO00003",
  partner_name_ar: "عميل التجزئة للديمو",
  partner_code: "DEMO-CUS-02",
  partner_phone: "01012345678",
  partner_address: "القاهرة",
  payment_methods: ["نقدي"],
  subtotal: "1000000",
  discount_amount: "0",
  transport_amount: "0",
  tax_amount: "0",
  original_total: "1000000",
  returned_total: "0",
  net_total: "1000000",
  paid: "0",
  refunded: "0",
  remaining: "1000000",
  notes: "",
  valid_until: null,
  card_number: "",
  vehicle_number: "",
  gross_weight_kg: "0",
  tare_weight_kg: "0",
  net_weight_kg: "0",
  lines: [
    {
      code: "4551",
      name: "ماسورة 200 مم 6 بار",
      quantity: "100",
      unit: "ماسورة",
      unit_price: "10000",
      line_total: "1000000",
      notes: "توريد للمصنع",
      actual_weight_kg: null,
      price_per_kg: null,
    },
  ],
  company: {
    name_ar: "ثري إيه بايب - 3A FOR PLASTIC PRODUCTS",
    phone: "01000000000، 01111111111، 01222222222",
    address: "المنوفية - سرس الليان",
    tax_number: "",
    currency_code: "EGP",
  },
};

const statementPreview: Statement = {
  company: preview.company,
  partner_phone: preview.partner_phone,
  detailed: true,
  include_drafts: false,
  invoice_details: {
    SI00003: preview.lines,
  },
  statement: {
    partner_code: "DEMO-CUS-02",
    partner_name_ar: "عميل التجزئة للديمو",
    date_from: "2026-08-01",
    date_to: "2026-08-31",
    opening_balance: "1500",
    closing_balance: "1001500",
    lines: [
      { movement_date: "2026-08-16T02:17:42+02:00", document_number: "SI00003", movement_type: "فاتورة مبيعات", debit: "1000000", credit: "0", running_balance: "1001500", notes: "فاتورة بيع تجريبية" },
    ],
  },
  summary: {
    opening_balance: "1500",
    standard_sales_total: "1000000",
    weight_sales_total: "0",
    returns_total: "0",
    receipts_total: "0",
    customer_refunds_total: "0",
    adjustments_total: "0",
    net_movement: "1000000",
    closing_balance: "1001500",
  },
};

const weightPreview: PrintDocument = {
  ...preview,
  document_type: "weight_invoice",
  document_title: "فاتورة مبيعات بالوزن / الكارتة",
  document_number: "SI-W-00003",
  card_number: "WC-00003",
  vehicle_number: "س ب ج 1234",
  gross_weight_kg: "5200",
  tare_weight_kg: "2200",
  net_weight_kg: "3000",
  lines: preview.lines.map((line) => ({
    ...line,
    quantity: "100",
    actual_weight_kg: "3000",
    price_per_kg: "333.333333",
  })),
};

export function PrintDesignPreviewPage() {
  if (window.location.search.includes("statement"))
    return <BrandedStatementPreview data={statementPreview} />;
  if (window.location.search.includes("weight"))
    return <BrandedDocumentPreview document={weightPreview} />;
  return <BrandedDocumentPreview document={preview} />;
}
